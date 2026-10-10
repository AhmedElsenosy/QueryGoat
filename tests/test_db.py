from sqlalchemy import text

from app.db import engine, ping_db


def test_postgres_connection() -> None:
    result = ping_db()
    assert result["ok"] is True
    assert result["user"] == "querygoat"
    assert result["database"] == "querygoat"


def test_select_one() -> None:
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
