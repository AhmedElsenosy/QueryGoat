from __future__ import annotations

from datetime import date, datetime, timezone

from app.db import SessionLocal, init_db
from app.models import AgentRun

from .graph import daily_graph
from .state import DailyState


def run_daily(puzzle_date: date | None = None, *, max_attempts: int = 5) -> DailyState:
    init_db()
    target = puzzle_date or datetime.now(timezone.utc).date()
    session = SessionLocal()
    try:
        run = AgentRun(puzzle_date=target, status="running", attempts=0)
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = str(run.id)
    finally:
        session.close()

    initial: DailyState = {
        "puzzle_date": target.isoformat(),
        "attempt": 1,
        "max_attempts": max_attempts,
        "skipped_ids": [],
        "reject_reasons": [],
        "status": "pending",
        "agent_run_id": run_id,
        "rewrite_attempt": 0,
        "max_rewrite_attempts": 3,
    }
    return daily_graph.invoke(initial)


def main() -> None:
    result = run_daily()
    print(
        "Daily picker:",
        {
            "status": result.get("status"),
            "puzzle_date": result.get("puzzle_date"),
            "attempts": result.get("attempt"),
            "daily_puzzle_id": result.get("daily_puzzle_id"),
            "notify_status": result.get("notify_status"),
            "notified_count": result.get("notified_count"),
            "error": result.get("error"),
        },
    )


if __name__ == "__main__":
    main()
