from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp

ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Except, exp.Intersect)
BLOCKED_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Attach,
    exp.Detach,
    exp.Pragma,
    exp.Command,
    exp.Transaction,
)


class UnsafeSQLError(ValueError):
    pass


class SQLExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    duration_ms: float
    truncated: bool


def parse_statements(sql: str) -> list[exp.Expression]:
    try:
        parsed = sqlglot.parse(sql, dialect="sqlite")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeSQLError(f"Could not parse SQL: {exc}") from exc
    statements = [stmt for stmt in parsed if stmt is not None]
    if not statements:
        raise UnsafeSQLError("Empty SQL.")
    return statements


def assert_safe_select(sql: str) -> exp.Expression:
    statements = parse_statements(sql)
    if len(statements) != 1:
        raise UnsafeSQLError("Only a single statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, ALLOWED_ROOTS):
        raise UnsafeSQLError("Only read-only SELECT queries are allowed.")
    for node in tree.walk():
        if isinstance(node, BLOCKED_TYPES):
            raise UnsafeSQLError(f"Forbidden SQL clause: {type(node).__name__}.")
        if isinstance(node, exp.Rand):
            raise UnsafeSQLError("Non-deterministic functions are not allowed.")
    lowered = sql.lower()
    if "load_extension" in lowered or "sqlite_temp_file_directory" in lowered:
        raise UnsafeSQLError("Forbidden SQLite function.")
    return tree


def has_order_by(sql: str) -> bool:
    try:
        tree = parse_statements(sql)[0]
    except UnsafeSQLError:
        return False
    return tree.find(exp.Order) is not None


def _canon(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float):
        return f"{value:.10g}"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def fingerprint(columns: list[str], rows: list[tuple], *, ordered: bool) -> str:
    norm_cols = [str(col).strip().lower() for col in columns]
    norm_rows = [tuple(_canon(v) for v in row) for row in rows]
    if not ordered:
        norm_rows = sorted(norm_rows)
    payload = json.dumps({"c": norm_cols, "r": norm_rows}, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def execute_readonly(
    sqlite_path: str | Path,
    sql: str,
    *,
    timeout_s: float = 2.0,
    max_rows: int = 200,
) -> QueryResult:
    path = Path(sqlite_path)
    if not path.is_file():
        raise SQLExecutionError(f"SQLite file not found: {path}")
    assert_safe_select(sql)

    started = time.perf_counter()
    dest = sqlite3.connect(":memory:")
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        src.backup(dest)
    finally:
        src.close()
    dest.execute("PRAGMA query_only=ON")

    aborted = False

    def _progress() -> int:
        nonlocal aborted
        if time.perf_counter() - started > timeout_s:
            aborted = True
            return 1
        return 0

    dest.set_progress_handler(_progress, 1000)
    try:
        cursor = dest.execute(sql)
        columns = [col[0] for col in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        if truncated:
            rows = rows[:max_rows]
    except sqlite3.Error as exc:
        if aborted:
            raise SQLExecutionError(f"Query timed out after {timeout_s:.1f}s.") from exc
        raise SQLExecutionError(str(exc)) from exc
    finally:
        dest.set_progress_handler(None, 0)
        dest.close()

    if aborted:
        raise SQLExecutionError(f"Query timed out after {timeout_s:.1f}s.")

    duration_ms = (time.perf_counter() - started) * 1000
    return QueryResult(
        columns=columns,
        rows=rows,
        duration_ms=duration_ms,
        truncated=truncated,
    )


def copy_sqlite(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())


def isolated_temp_copy(sqlite_path: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    handle.close()
    Path(handle.name).write_bytes(Path(sqlite_path).read_bytes())
    return Path(handle.name)
