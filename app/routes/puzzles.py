from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import SRC_DIR
from app.db import get_db
from app.deps import get_current_user
from app.models import DailyPuzzle, Question, Submission, User
from app.schema_inspector import build_schema_context
from app.schemas import (
    ColumnInfo,
    DailyPuzzlePublic,
    ForeignKeyInfo,
    OutputShape,
    SubmitTodayRequest,
    SubmitTodayResponse,
    TableInfo,
)
from app.services.grader import grade_submission

router = APIRouter(prefix="/puzzles", tags=["puzzles"])


def _resolve_sqlite_path(question: Question) -> Path:
    sqlite_rel = question.database.sqlite_path
    path = Path(sqlite_rel)
    return path if path.is_absolute() else SRC_DIR / sqlite_rel


@router.get("/today", response_model=DailyPuzzlePublic)
def today(db: Session = Depends(get_db)) -> DailyPuzzlePublic:
    puzzle_date = datetime.now(timezone.utc).date()
    puzzle = db.execute(
        select(DailyPuzzle)
        .options(joinedload(DailyPuzzle.question).joinedload(Question.database))
        .where(DailyPuzzle.puzzle_date == puzzle_date)
    ).scalar_one_or_none()
    if puzzle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Today's puzzle has not been published yet.",
        )
    question = puzzle.question

    # Resolve SQLite path (stored relative to SRC_DIR)
    sqlite_rel = question.database.sqlite_path
    sqlite_path = (
        Path(sqlite_rel) if Path(sqlite_rel).is_absolute()
        else SRC_DIR / sqlite_rel
    )

    # Build schema context on the fly from the SQLite file
    context = build_schema_context(
        sqlite_path,
        question.gold_sql,
        question.result_row_count,
        question.result_col_count or 1,
    )

    schema_info = [
        TableInfo(
            name=t["name"],
            columns=[ColumnInfo(**c) for c in t["columns"]],
            foreign_keys=[ForeignKeyInfo(**fk) for fk in t["foreign_keys"]],
            sample_columns=t["sample_columns"],
            sample_rows=t["sample_rows"],
        )
        for t in context["tables"]
    ]

    return DailyPuzzlePublic(
        puzzle_date=puzzle.puzzle_date.isoformat(),
        prompt=question.rewritten_prompt or question.prompt,
        difficulty=question.difficulty,
        database=question.database.display_name,
        schema_info=schema_info,
        output_shape=OutputShape(**context["output_shape"]),
    )


@router.post("/today/submit", response_model=SubmitTodayResponse)
def submit_today(
    body: SubmitTodayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubmitTodayResponse:
    puzzle_date = datetime.now(timezone.utc).date()
    puzzle = db.execute(
        select(DailyPuzzle)
        .options(joinedload(DailyPuzzle.question).joinedload(Question.database))
        .where(DailyPuzzle.puzzle_date == puzzle_date)
    ).scalar_one_or_none()
    if puzzle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Today's puzzle has not been published yet.",
        )
    question = puzzle.question

    grade = grade_submission(
        _resolve_sqlite_path(question),
        body.sql,
        question.gold_sql,
        ordered=question.result_ordered,
    )

    already_solved = db.execute(
        select(Submission.id).where(
            Submission.user_id == current_user.id,
            Submission.question_id == question.id,
            Submission.is_correct.is_(True),
        )
    ).scalar_one_or_none() is not None

    error_message = grade.error_message if grade.status != "wrong" else None
    if grade.is_correct and not already_solved:
        db.add(
            Submission(
                user_id=current_user.id,
                question_id=question.id,
                puzzle_date=puzzle.puzzle_date,
                sql=body.sql,
                is_correct=True,
                duration_ms=grade.duration_ms,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    elif not grade.is_correct:
        db.add(
            Submission(
                user_id=current_user.id,
                question_id=question.id,
                puzzle_date=puzzle.puzzle_date,
                sql=body.sql,
                is_correct=False,
                error_message=error_message,
                duration_ms=grade.duration_ms,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    attempts = db.execute(
        select(func.count())
        .select_from(Submission)
        .where(
            Submission.user_id == current_user.id,
            Submission.question_id == question.id,
        )
    ).scalar_one()

    messages = {
        "correct": "Correct! You solved today's puzzle."
        if not already_solved
        else "Correct — already solved. Checking new attempt.",
        "wrong": "Wrong — your query ran, but the result doesn't match.",
        "too_many_rows": grade.error_message or "Query returned too many rows.",
        "timeout": "Query timed out.",
        "sql_error": grade.error_message or "Invalid SQL.",
        "cheat": grade.error_message or "Nice try — queries must read the tables.",
    }
    return SubmitTodayResponse(
        is_correct=grade.is_correct,
        status=grade.status,
        message=messages.get(grade.status, messages["sql_error"]),
        attempts=int(attempts),
        solved=already_solved or grade.is_correct,
        puzzle_date=puzzle.puzzle_date.isoformat(),
    )
