from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import SRC_DIR
from app.db import get_db
from app.models import DailyPuzzle, Question
from app.schema_inspector import build_schema_context
from app.schemas import (
    ColumnInfo,
    DailyPuzzlePublic,
    ForeignKeyInfo,
    OutputShape,
    TableInfo,
)

router = APIRouter(prefix="/puzzles", tags=["puzzles"])


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
