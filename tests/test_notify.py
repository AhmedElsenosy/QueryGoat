import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.run_daily import run_daily
from app.db import SessionLocal
from app.main import app
from app.models import DailyPuzzle, User
from tests.conftest import fake_email_calls

client = TestClient(app)


def _register_user() -> None:
    suffix = uuid.uuid4().hex[:8]
    response = client.post("/auth/register", json={
        "username": f"goatmail{suffix}",
        "gmail": f"goatmail{suffix}@gmail.com",
        "password": "hammer-bill-grip9",
    })
    assert response.status_code == 201, response.text


def _set_notified(value: datetime | None) -> None:
    session = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()
        puzzle = session.execute(
            select(DailyPuzzle).where(DailyPuzzle.puzzle_date == today)
        ).scalar_one()
        puzzle.notified_at = value
        session.commit()
    finally:
        session.close()


def test_announcement_sent_once_per_day() -> None:
    _register_user()
    _set_notified(None)

    first = run_daily()
    assert first["status"] == "already_published"
    assert first["notify_status"] == "sent", first

    calls = fake_email_calls()
    assert len(calls) == 1
    announce = calls[0]

    session = SessionLocal()
    try:
        active = session.execute(
            select(User.email).where(User.is_active.is_(True))
        ).scalars().all()
    finally:
        session.close()
    assert set(announce["recipients"]) == set(active)
    assert "puzzle just went live" in announce["body"]
    assert "Solve it now" in announce["body"]

    session = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()
        puzzle = session.execute(
            select(DailyPuzzle).where(DailyPuzzle.puzzle_date == today)
        ).scalar_one()
        assert puzzle.notified_at is not None
    finally:
        session.close()

    fake_email_calls().clear()
    second = run_daily()
    assert second["notify_status"] == "already_notified"
    assert not fake_email_calls()
