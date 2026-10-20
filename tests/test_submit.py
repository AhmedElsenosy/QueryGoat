import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.run_daily import run_daily
from app.db import SessionLocal
from app.main import app
from app.models import DailyPuzzle, User

client = TestClient(app)


def _register_and_login() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    user_body = {
        "username": f"goat{suffix}",
        "gmail": f"goat{suffix}@gmail.com",
        "password": "hammer-bill-grip9",
    }
    response = client.post("/auth/register", json=user_body)
    assert response.status_code == 201, response.text
    login = client.post("/auth/login", json={
        "username": user_body["username"],
        "password": user_body["password"],
    })
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _todays_gold_sql() -> str:
    run_daily()
    session = SessionLocal()
    try:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date()
        puzzle = session.execute(
            select(DailyPuzzle).where(DailyPuzzle.puzzle_date == today)
        ).scalar_one()
        return puzzle.question.gold_sql
    finally:
        session.close()


def test_submit_requires_auth() -> None:
    response = client.post("/puzzles/today/submit", json={"sql": "SELECT 1"})
    assert response.status_code == 401


def test_submit_correct_query_solves_puzzle() -> None:
    headers = _register_and_login()
    gold = _todays_gold_sql()
    response = client.post(
        "/puzzles/today/submit", json={"sql": gold}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_correct"] is True
    assert body["status"] == "correct"
    assert body["solved"] is True
    assert body["attempts"] == 1

    wrapped = "SELECT * FROM (" + gold + ") AS wrapped"
    again = client.post(
        "/puzzles/today/submit", json={"sql": wrapped}, headers=headers
    )
    assert again.status_code == 200
    assert again.json()["is_correct"] is True
    assert again.json()["solved"] is True


def test_submit_wrong_query_records_attempts() -> None:
    headers = _register_and_login()
    wrong = "SELECT COUNT(*) AS n FROM sqlite_master"
    first = client.post("/puzzles/today/submit", json={"sql": wrong}, headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["is_correct"] is False
    assert body["status"] == "wrong"
    assert body["attempts"] == 1
    assert body["solved"] is False

    second = client.post("/puzzles/today/submit", json={"sql": wrong}, headers=headers)
    assert second.json()["attempts"] == 2
    assert second.json()["solved"] is False


def test_submit_rejects_unsafe_and_broken_sql() -> None:
    headers = _register_and_login()
    _todays_gold_sql()
    for sql in ("DROP TABLE users", "SELECT (", "INSERT INTO users VALUES ('x')"):
        response = client.post("/puzzles/today/submit", json={"sql": sql}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_correct"] is False
        assert body["status"] == "sql_error"
        assert body["message"]


def test_submit_rejects_constant_only_queries() -> None:
    headers = _register_and_login()
    cheats = [
        "SELECT 0.99",
        "SELECT 0.99 AS answer",
        "SELECT (SELECT 0.99)",
        "SELECT 0.99 AS x FROM Genre LIMIT 1",
        "WITH c AS (SELECT GenreId FROM Genre) SELECT 0.99",
    ]
    for sql in cheats:
        response = client.post("/puzzles/today/submit", json={"sql": sql}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_correct"] is False, sql
        assert body["status"] == "cheat", sql
        assert body["attempts"] >= 1, sql
        assert body["solved"] is False, sql


def test_submit_never_leaks_gold() -> None:
    headers = _register_and_login()
    payload = client.post("/puzzles/today/submit", json={"sql": "SELECT COUNT(*) AS n FROM sqlite_master"}, headers=headers).json()
    text = str(payload).lower()
    assert "gold_sql" not in text
    assert "goldsql" not in text


def test_submit_gold_execution_matches_stored_fingerprint() -> None:
    # Grading compares value fingerprints of live executions; gold vs gold
    # must always be a pass.
    headers = _register_and_login()
    gold = _todays_gold_sql()
    response = client.post("/puzzles/today/submit", json={"sql": gold}, headers=headers)
    assert response.json()["is_correct"] is True


def test_sandbox_declares_data_usage_helpers() -> None:
    from app.sandbox import CheatSQLError, assert_uses_data

    with pytest.raises(CheatSQLError):
        assert_uses_data("SELECT 0.99")
    assert_uses_data("SELECT COUNT(*) FROM artists")
