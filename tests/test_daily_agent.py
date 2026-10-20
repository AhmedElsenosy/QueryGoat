from fastapi.testclient import TestClient

from app.agent.run_daily import run_daily
from app.main import app

client = TestClient(app)


def test_run_daily_is_idempotent() -> None:
    first = run_daily()
    assert first["status"] in {"published", "already_published"}
    assert first.get("daily_puzzle_id")
    second = run_daily()
    assert second["status"] == "already_published"
    assert second["daily_puzzle_id"] == first["daily_puzzle_id"]


def test_puzzles_today_hides_gold_sql() -> None:
    run_daily()
    response = client.get("/puzzles/today")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["prompt"]
    assert body["difficulty"] in {"medium", "hard"}
    assert body["database"]
    assert "gold_sql" not in body
    assert "goldSql" not in body
