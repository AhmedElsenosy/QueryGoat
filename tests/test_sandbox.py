import sqlite3
from pathlib import Path

import pytest

from app.ingest.filters import classify_difficulty, is_select_star, normalize_sql
from app.sandbox import (
    SQLExecutionError,
    UnsafeSQLError,
    execute_readonly,
    fingerprint,
    value_fingerprint,
)


def _make_db(tmp_path: Path) -> Path:
    path = tmp_path / "toy.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE artists (id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO artists (name) VALUES ('A'), ('B'), ('C');
        """
    )
    conn.close()
    return path


def test_sandbox_runs_select(tmp_path: Path) -> None:
    path = _make_db(tmp_path)
    result = execute_readonly(path, "SELECT name FROM artists ORDER BY name")
    assert result.columns == ["name"]
    assert [row[0] for row in result.rows] == ["A", "B", "C"]
    assert result.truncated is False


def test_sandbox_rejects_writes(tmp_path: Path) -> None:
    path = _make_db(tmp_path)
    with pytest.raises(UnsafeSQLError):
        execute_readonly(path, "INSERT INTO artists (name) VALUES ('Z')")
    with pytest.raises(UnsafeSQLError):
        execute_readonly(path, "SELECT 1; SELECT 2")
    with pytest.raises(UnsafeSQLError):
        execute_readonly(path, "PRAGMA table_info(artists)")


def test_sandbox_caps_rows(tmp_path: Path) -> None:
    path = _make_db(tmp_path)
    result = execute_readonly(path, "SELECT name FROM artists", max_rows=1)
    assert result.truncated is True
    assert len(result.rows) == 1


def test_fingerprint_ignores_order_unless_asked() -> None:
    cols = ["n"]
    a = [("b",), ("a",)]
    b = [("a",), ("b",)]
    assert fingerprint(cols, a, ordered=False) == fingerprint(cols, b, ordered=False)
    assert fingerprint(cols, a, ordered=True) != fingerprint(cols, b, ordered=True)


def test_fingerprint_still_includes_columns_by_default() -> None:
    assert fingerprint(["a"], [("x",)], ordered=False) != fingerprint(
        ["b"], [("x",)], ordered=False
    )


def test_value_fingerprint_ignores_column_labels(tmp_path: Path) -> None:
    path = _make_db(tmp_path)
    gold = execute_readonly(path, "SELECT name FROM artists WHERE name = 'A'")
    variants = [
        "SELECT T1.name AS artist_name FROM artists T1 WHERE T1.name = 'A'",
        "SELECT a.name AS label FROM artists a WHERE a.name = 'A'",
    ]
    gold_hash = value_fingerprint(gold.columns, gold.rows, ordered=True)
    for sql in variants:
        result = execute_readonly(path, sql)
        assert result.columns != gold.columns
        assert value_fingerprint(
            result.columns, result.rows, ordered=True
        ) == gold_hash, f"variant marked wrong: {sql}"


def test_value_fingerprint_matches_for_aggregate_aliases(tmp_path: Path) -> None:
    path = _make_db(tmp_path)
    gold = execute_readonly(path, "SELECT COUNT(*) FROM artists")
    user = execute_readonly(path, "SELECT COUNT(id) AS total FROM artists")
    assert gold.rows == user.rows
    assert value_fingerprint(
        gold.columns, gold.rows, ordered=False
    ) == value_fingerprint(user.columns, user.rows, ordered=False)
    assert fingerprint(gold.columns, gold.rows, ordered=False) != fingerprint(
        user.columns, user.rows, ordered=False
    )


def test_difficulty_and_star_filters() -> None:
    assert classify_difficulty("SELECT count(*) FROM album") == "easy"
    assert (
        classify_difficulty(
            "SELECT T1.name FROM artist AS T1 JOIN album AS T2 ON T1.id = T2.artist_id"
        )
        == "medium"
    )
    assert is_select_star("SELECT * FROM album")
    assert normalize_sql("SELECT  A") == "select a"


def test_missing_sqlite_file(tmp_path: Path) -> None:
    with pytest.raises(SQLExecutionError):
        execute_readonly(tmp_path / "nope.sqlite", "SELECT 1")
