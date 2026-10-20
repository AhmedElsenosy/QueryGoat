from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.config import SRC_DIR
from app.db import SessionLocal
from app.ingest.curated import DAILY_DIFFICULTIES, MAX_DAILY_ROWS
from app.models import AgentRun, DailyPuzzle, PuzzleDatabase, Question
from app.sandbox import SQLExecutionError, UnsafeSQLError, execute_readonly, fingerprint

from .state import DailyState

log = logging.getLogger(__name__)

RECENT_DB_WINDOW = 5


def _today(state: DailyState) -> date:
    return date.fromisoformat(state["puzzle_date"])


def _resolve_sqlite(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        return path
    return SRC_DIR / path


def _finish_run(run_id: str, **fields: object) -> None:
    session = SessionLocal()
    try:
        run = session.get(AgentRun, uuid.UUID(run_id))
        if run is None:
            return
        for key, value in fields.items():
            setattr(run, key, value)
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        session.close()


def _clean_sql_response(text: str) -> str:
    """Strip markdown code fences from LLM-generated SQL."""
    text = text.strip()
    if text.startswith("```sql"):
        text = text[6:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


# ── already_published ─────────────────────────────────────────────────

def already_published(state: DailyState) -> DailyState:
    session = SessionLocal()
    try:
        existing = session.execute(
            select(DailyPuzzle).where(DailyPuzzle.puzzle_date == _today(state))
        ).scalar_one_or_none()
        if existing is None:
            return {"status": "pending"}
        _finish_run(
            state["agent_run_id"],
            status="already_published",
            attempts=state.get("attempt", 1),
            selected_question_id=existing.question_id,
        )
        return {
            "status": "already_published",
            "daily_puzzle_id": str(existing.id),
            "candidate_id": str(existing.question_id),
        }
    finally:
        session.close()


# ── select_candidate ──────────────────────────────────────────────────

def select_candidate(state: DailyState) -> DailyState:
    skipped = [uuid.UUID(item) for item in state.get("skipped_ids", [])]
    session = SessionLocal()
    try:
        recent_db_ids = session.execute(
            select(Question.database_id)
            .join(DailyPuzzle, DailyPuzzle.question_id == Question.id)
            .order_by(DailyPuzzle.puzzle_date.desc())
            .limit(RECENT_DB_WINDOW)
        ).scalars().all()

        def pool(exclude_recent: bool):
            stmt = (
                select(Question)
                .join(PuzzleDatabase, PuzzleDatabase.id == Question.database_id)
                .where(
                    Question.eligible_for_daily.is_(True),
                    Question.used_as_daily_on.is_(None),
                    Question.difficulty.in_(DAILY_DIFFICULTIES),
                    PuzzleDatabase.is_active.is_(True),
                )
                .options(joinedload(Question.database))
                .order_by(func.random())
            )
            if skipped:
                stmt = stmt.where(Question.id.notin_(skipped))
            if exclude_recent and recent_db_ids:
                stmt = stmt.where(Question.database_id.notin_(recent_db_ids))
            return session.execute(stmt).unique().scalars().first()

        question = pool(exclude_recent=True) or pool(exclude_recent=False)
        if question is None:
            return {
                "status": "failed",
                "candidate_id": None,
                "error": "No unused medium/hard questions left in the bank.",
            }
        return {
            "status": "pending",
            "candidate_id": str(question.id),
            "gold_sql": question.gold_sql,
            "sqlite_path": str(_resolve_sqlite(question.database.sqlite_path)),
            "result_hash_stored": question.result_hash,
            "result_ordered": question.result_ordered,
            "validation_errors": [],
            "result_hash_live": None,
            "live_row_count": None,
            "result_col_count": None,
            "truncated": False,
            # Reset rewrite state for the new candidate
            "rewritten_prompt": None,
            "rewrite_attempt": 0,
            "schema_context": None,
        }
    finally:
        session.close()


# ── execute_gold ──────────────────────────────────────────────────────

def execute_gold(state: DailyState) -> DailyState:
    sql = state.get("gold_sql")
    sqlite_path = state.get("sqlite_path")
    if not sql or not sqlite_path:
        return {"validation_errors": ["Missing gold SQL or sqlite path."]}
    try:
        result = execute_readonly(
            sqlite_path,
            sql,
            timeout_s=2.0,
            max_rows=MAX_DAILY_ROWS,
        )
    except (UnsafeSQLError, SQLExecutionError) as exc:
        return {"validation_errors": [str(exc)]}
    live_hash = fingerprint(
        result.columns, result.rows, ordered=bool(state.get("result_ordered"))
    )
    return {
        "validation_errors": [],
        "result_hash_live": live_hash,
        "live_row_count": len(result.rows),
        "result_col_count": len(result.columns),
        "truncated": result.truncated,
    }


# ── validate_result ───────────────────────────────────────────────────

def validate_result(state: DailyState) -> DailyState:
    errors = list(state.get("validation_errors") or [])
    rows = state.get("live_row_count")
    if state.get("result_hash_live") is None:
        errors.append("Gold SQL did not produce a live fingerprint.")
    if rows is None or rows < 1:
        errors.append("Result set is empty.")
    if rows is not None and rows > MAX_DAILY_ROWS:
        errors.append("Result set is too large for a daily puzzle.")
    if state.get("truncated"):
        errors.append("Result set exceeded the row cap.")
    stored = state.get("result_hash_stored")
    live = state.get("result_hash_live")
    if stored and live and stored != live:
        errors.append("Live result hash does not match the ingested fingerprint.")
    if errors:
        reasons = list(state.get("reject_reasons") or [])
        reasons.append(
            {
                "question_id": state.get("candidate_id"),
                "errors": errors,
            }
        )
        return {
            "status": "rejected",
            "validation_errors": errors,
            "reject_reasons": reasons,
        }
    return {"status": "ready_to_publish", "validation_errors": []}


# ── rewrite_prompt (NEW) ──────────────────────────────────────────────

def rewrite_prompt(state: DailyState) -> DailyState:
    """Use LLM to rewrite the Spider caption into a LeetCode-style problem."""
    from app.agent.prompts import REWRITE_SYSTEM, REWRITE_USER
    from app.schema_inspector import build_schema_context, schema_to_text

    sqlite_path = state.get("sqlite_path")
    gold_sql = state.get("gold_sql")
    if not sqlite_path or not gold_sql:
        return {"status": "skip_rewrite"}

    # Build schema context (needed for both LLM prompt and API response)
    result_col_count = state.get("result_col_count") or 1
    live_row_count = state.get("live_row_count") or 1
    schema_context = build_schema_context(
        sqlite_path, gold_sql, live_row_count, result_col_count,
    )
    schema_text = schema_to_text(schema_context)

    # Fetch original prompt from DB
    session = SessionLocal()
    try:
        question = session.get(Question, uuid.UUID(state["candidate_id"]))
        original_prompt = question.prompt if question else "Unknown"
    finally:
        session.close()

    # Try LLM rewrite
    try:
        from app.llm import get_llm_provider
        llm = get_llm_provider()
        user_prompt = REWRITE_USER.format(
            original_prompt=original_prompt,
            schema_text=schema_text,
        )
        rewritten = llm.generate(user_prompt, system=REWRITE_SYSTEM)
        log.info("Rewrite attempt %d: %s", state.get("rewrite_attempt", 0) + 1, rewritten[:120])
    except Exception as exc:
        log.warning("LLM rewrite failed, using original prompt: %s", exc)
        return {
            "status": "skip_rewrite",
            "rewritten_prompt": original_prompt,
            "schema_context": schema_context,
            "result_col_count": result_col_count,
        }

    rewrite_attempt = int(state.get("rewrite_attempt", 0)) + 1
    return {
        "rewritten_prompt": rewritten,
        "schema_context": schema_context,
        "rewrite_attempt": rewrite_attempt,
        "result_col_count": result_col_count,
    }


# ── verify_rewrite (NEW) ─────────────────────────────────────────────

def verify_rewrite(state: DailyState) -> DailyState:
    """Have a second LLM call write SQL from only the rewrite + schema.

    If the generated SQL produces the same result set as the gold SQL,
    the rewrite is faithful.  Otherwise retry or reject.
    """
    from app.agent.prompts import VERIFY_SYSTEM, VERIFY_USER
    from app.schema_inspector import schema_to_text

    rewritten = state.get("rewritten_prompt")
    schema_context = state.get("schema_context")
    sqlite_path = state.get("sqlite_path")

    if not rewritten or not schema_context or not sqlite_path:
        return {"status": "verified"}

    schema_text = schema_to_text(schema_context)
    col_count = schema_context["output_shape"]["columns"]
    row_count = schema_context["output_shape"]["rows"]

    attempt = int(state.get("rewrite_attempt", 1))
    max_rewrite = int(state.get("max_rewrite_attempts", 3))

    # Generate SQL from the rewrite
    try:
        from app.llm import get_llm_provider
        llm = get_llm_provider()
        user_prompt = VERIFY_USER.format(
            rewritten_prompt=rewritten,
            schema_text=schema_text,
            col_count=col_count,
            row_count=row_count,
        )
        generated_sql = _clean_sql_response(
            llm.generate(user_prompt, system=VERIFY_SYSTEM)
        )
        log.info("Verification SQL: %s", generated_sql[:200])
    except Exception as exc:
        log.warning("LLM verification call failed, accepting rewrite: %s", exc)
        return {"status": "verified"}

    # Execute the generated SQL and compare fingerprints
    try:
        result = execute_readonly(
            sqlite_path, generated_sql, timeout_s=2.0, max_rows=MAX_DAILY_ROWS,
        )
        ordered = bool(state.get("result_ordered"))
        verify_hash = fingerprint(result.columns, result.rows, ordered=ordered)
    except (UnsafeSQLError, SQLExecutionError) as exc:
        log.warning("Verification SQL execution failed: %s", exc)
        if attempt < max_rewrite:
            return {"status": "rewrite_retry"}
        log.warning("Max rewrite attempts reached, rejecting question.")
        reasons = list(state.get("reject_reasons") or [])
        reasons.append({
            "question_id": state.get("candidate_id"),
            "errors": [f"Rewrite verification SQL error after {attempt} attempts: {exc}"],
        })
        return {"status": "rejected", "reject_reasons": reasons}

    gold_hash = state.get("result_hash_live") or state.get("result_hash_stored")
    if verify_hash == gold_hash:
        log.info("Rewrite verified — fingerprints match.")
        return {"status": "verified"}

    # Hash mismatch — rewrite wasn't faithful
    log.warning(
        "Rewrite verification hash mismatch (attempt %d/%d): expected %s, got %s",
        attempt, max_rewrite, gold_hash, verify_hash,
    )
    if attempt < max_rewrite:
        return {"status": "rewrite_retry"}

    # Max retries — reject this question, pick another candidate
    reasons = list(state.get("reject_reasons") or [])
    reasons.append({
        "question_id": state.get("candidate_id"),
        "errors": [f"Rewrite verification failed after {attempt} attempts."],
    })
    return {"status": "rejected", "reject_reasons": reasons}


# ── retry ─────────────────────────────────────────────────────────────

def retry(state: DailyState) -> DailyState:
    skipped = list(state.get("skipped_ids") or [])
    candidate = state.get("candidate_id")
    if candidate and candidate not in skipped:
        skipped.append(candidate)
    attempt = int(state.get("attempt") or 1) + 1
    max_attempts = int(state.get("max_attempts") or 5)
    if attempt > max_attempts:
        return {
            "attempt": attempt,
            "skipped_ids": skipped,
            "status": "failed",
            "error": "Max daily-picker attempts exceeded.",
        }
    return {
        "attempt": attempt,
        "skipped_ids": skipped,
        "status": "pending",
        "candidate_id": None,
        "gold_sql": None,
        "error": None,
    }


# ── publish ───────────────────────────────────────────────────────────

def publish(state: DailyState) -> DailyState:
    question_id = uuid.UUID(state["candidate_id"])
    run_id = uuid.UUID(state["agent_run_id"])
    puzzle_date = _today(state)
    session = SessionLocal()
    try:
        question = session.get(Question, question_id)
        if question is None:
            return {"status": "rejected", "validation_errors": ["Candidate disappeared."]}
        puzzle = DailyPuzzle(
            puzzle_date=puzzle_date,
            question_id=question.id,
            agent_run_id=run_id,
        )
        question.used_as_daily_on = puzzle_date
        # Store rewritten prompt and column count
        rewritten = state.get("rewritten_prompt")
        if rewritten:
            question.rewritten_prompt = rewritten
        col_count = state.get("result_col_count")
        if col_count:
            question.result_col_count = col_count
        session.add(puzzle)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.execute(
                select(DailyPuzzle).where(DailyPuzzle.puzzle_date == puzzle_date)
            ).scalar_one()
            _finish_run(
                state["agent_run_id"],
                status="already_published",
                attempts=state.get("attempt", 1),
                selected_question_id=existing.question_id,
                reject_reasons=state.get("reject_reasons") or [],
            )
            return {
                "status": "already_published",
                "daily_puzzle_id": str(existing.id),
            }
        session.refresh(puzzle)
        _finish_run(
            state["agent_run_id"],
            status="published",
            attempts=state.get("attempt", 1),
            selected_question_id=question.id,
            reject_reasons=state.get("reject_reasons") or [],
        )
        return {
            "status": "published",
            "daily_puzzle_id": str(puzzle.id),
        }
    finally:
        session.close()


# ── fail_run ──────────────────────────────────────────────────────────

def fail_run(state: DailyState) -> DailyState:
    _finish_run(
        state["agent_run_id"],
        status="failed",
        attempts=state.get("attempt", 1),
        reject_reasons=state.get("reject_reasons") or [],
        error=state.get("error") or "Daily picker failed.",
    )
    return {"status": "failed"}
