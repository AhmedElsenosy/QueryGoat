"""Submission grading core.

User SQL is executed server-side in the sandbox and graded by comparing
value fingerprints (rows only, no column labels) against the gold result,
which is re-executed live against the puzzle SQLite file at grading time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.ingest.curated import MAX_DAILY_ROWS
from app.sandbox import (
    CheatSQLError,
    SQLExecutionError,
    UnsafeSQLError,
    assert_uses_data,
    execute_readonly,
    value_fingerprint,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GradeResult:
    status: str  # "correct" | "wrong" | "sql_error" | "timeout" | "too_many_rows" | "cheat"
    is_correct: bool
    error_message: str | None
    duration_ms: float


def grade_submission(
    sqlite_path: str | Path,
    user_sql: str,
    gold_sql: str,
    *,
    ordered: bool,
    max_rows: int = MAX_DAILY_ROWS,
) -> GradeResult:
    """Execute *user_sql* and compare its result values to the gold result.

    Raises nothing for user mistakes — those are gradable outcomes.  Only
    unexpected server-side problems (e.g. missing sqlite file) propagate.
    """
    try:
        assert_uses_data(user_sql)
    except (CheatSQLError, UnsafeSQLError) as exc:
        status = "cheat" if isinstance(exc, CheatSQLError) else "sql_error"
        return GradeResult(
            status=status, is_correct=False, error_message=str(exc), duration_ms=0.0
        )

    # User execution first: bad SQL never reaches gold re-execution.
    try:
        user_result = execute_readonly(
            sqlite_path, user_sql, timeout_s=2.0, max_rows=max_rows
        )
    except UnsafeSQLError as exc:
        return GradeResult(
            status="sql_error", is_correct=False, error_message=str(exc), duration_ms=0.0
        )
    except SQLExecutionError as exc:
        message = str(exc)
        status = "timeout" if "timed out" in message else "sql_error"
        return GradeResult(
            status=status, is_correct=False, error_message=message, duration_ms=0.0
        )

    if user_result.truncated:
        return GradeResult(
            status="too_many_rows",
            is_correct=False,
            error_message=f"Query returned more than {max_rows} rows.",
            duration_ms=user_result.duration_ms,
        )

    gold_result = execute_readonly(sqlite_path, gold_sql, timeout_s=2.0, max_rows=max_rows)

    user_hash = value_fingerprint(
        user_result.columns, user_result.rows, ordered=ordered
    )
    gold_hash = value_fingerprint(
        gold_result.columns, gold_result.rows, ordered=ordered
    )
    is_correct = user_hash == gold_hash
    if not is_correct:
        log.info("Submission hash mismatch: user=%s gold=%s", user_hash[:12], gold_hash[:12])
    return GradeResult(
        status="correct" if is_correct else "wrong",
        is_correct=is_correct,
        error_message=None,
        duration_ms=user_result.duration_ms,
    )
