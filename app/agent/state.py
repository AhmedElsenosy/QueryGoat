from __future__ import annotations

from typing import Any, TypedDict


class DailyState(TypedDict, total=False):
    puzzle_date: str
    attempt: int
    max_attempts: int
    skipped_ids: list[str]
    candidate_id: str | None
    gold_sql: str | None
    sqlite_path: str | None
    result_hash_stored: str | None
    result_ordered: bool
    result_hash_live: str | None
    live_row_count: int | None
    result_col_count: int | None
    truncated: bool
    validation_errors: list[str]
    reject_reasons: list[dict[str, Any]]
    status: str
    daily_puzzle_id: str | None
    agent_run_id: str
    error: str | None
    # Prompt rewrite fields
    rewritten_prompt: str | None
    rewrite_attempt: int
    max_rewrite_attempts: int
    schema_context: dict | None
    # Notification fields
    notify_status: str | None
    notified_count: int | None
