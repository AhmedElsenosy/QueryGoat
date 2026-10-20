"""Extract schema, sample rows, and foreign keys from SQLite puzzle databases.

Everything is read on the fly from the SQLite file so it cannot drift
from the data the sandbox actually executes queries against.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


# ---------------------------------------------------------------------------
# Table extraction from gold SQL
# ---------------------------------------------------------------------------

def extract_used_tables(gold_sql: str) -> list[str]:
    """Parse *gold_sql* with sqlglot and return referenced table names."""
    try:
        parsed = sqlglot.parse(gold_sql, dialect="sqlite")
    except sqlglot.errors.ParseError:
        return []
    tables: set[str] = set()
    for stmt in parsed:
        if stmt is None:
            continue
        for table_node in stmt.find_all(exp.Table):
            name = table_node.name
            if name:
                tables.add(name)
    return sorted(tables)


# ---------------------------------------------------------------------------
# SQLite introspection helpers
# ---------------------------------------------------------------------------

def get_all_tables(sqlite_path: Path) -> list[str]:
    """Return every user table name in the database."""
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_table_info(sqlite_path: Path, table_name: str) -> list[dict[str, Any]]:
    """Column metadata via ``PRAGMA table_info``."""
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        return [
            {"name": r[1], "type": r[2] or "TEXT", "pk": bool(r[5])}
            for r in rows
        ]
    finally:
        conn.close()


def get_foreign_keys(sqlite_path: Path, table_name: str) -> list[dict[str, str]]:
    """Foreign-key relationships via ``PRAGMA foreign_key_list``."""
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(f'PRAGMA foreign_key_list("{table_name}")').fetchall()
        return [
            {"from_column": r[3], "to_table": r[2], "to_column": r[4]}
            for r in rows
        ]
    finally:
        conn.close()


def _sanitize(value: object) -> object:
    """Make a SQLite cell JSON-serialisable."""
    if isinstance(value, bytes):
        return value.hex()
    return value


def get_sample_rows(
    sqlite_path: Path,
    table_name: str,
    limit: int = 5,
) -> tuple[list[str], list[list]]:
    """Return ``(column_names, rows)`` with up to *limit* sample rows."""
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        cursor = conn.execute(f'SELECT * FROM "{table_name}" LIMIT ?', (limit,))
        col_names = [d[0] for d in cursor.description] if cursor.description else []
        rows = [[_sanitize(v) for v in row] for row in cursor.fetchall()]
        return col_names, rows
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# High-level context builder
# ---------------------------------------------------------------------------

def build_schema_context(
    sqlite_path: str | Path,
    gold_sql: str,
    result_row_count: int,
    result_col_count: int,
    *,
    sample_limit: int = 5,
) -> dict:
    """Build the full puzzle context for a question.

    Only includes tables referenced by *gold_sql*.  Falls back to every
    table in the database when sqlglot cannot parse the query.
    """
    path = Path(sqlite_path)
    used_tables = extract_used_tables(gold_sql)

    # Map parsed names → real table names (case-insensitive)
    all_tables = get_all_tables(path)
    all_lower: dict[str, str] = {t.lower(): t for t in all_tables}
    resolved = []
    for t in used_tables:
        real = all_lower.get(t.lower())
        if real and real not in resolved:
            resolved.append(real)
    if not resolved:
        resolved = all_tables  # fallback

    tables: list[dict] = []
    for table_name in resolved:
        columns = get_table_info(path, table_name)
        if not columns:
            continue
        foreign_keys = get_foreign_keys(path, table_name)
        col_names, sample_rows = get_sample_rows(
            path, table_name, limit=sample_limit,
        )
        tables.append(
            {
                "name": table_name,
                "columns": columns,
                "foreign_keys": foreign_keys,
                "sample_columns": col_names,
                "sample_rows": sample_rows,
            }
        )

    return {
        "tables": tables,
        "output_shape": {
            "columns": result_col_count,
            "rows": result_row_count,
        },
    }


# ---------------------------------------------------------------------------
# Plain-text renderer (for LLM prompts)
# ---------------------------------------------------------------------------

def schema_to_text(context: dict) -> str:
    """Render *context* as plain text suitable for an LLM prompt."""
    lines: list[str] = []
    for table in context["tables"]:
        lines.append(f"Table: {table['name']}")
        lines.append("-" * 40)
        for col in table["columns"]:
            pk = " (PK)" if col.get("pk") else ""
            lines.append(f"  {col['name']}  {col['type']}{pk}")
        for fk in table.get("foreign_keys", []):
            lines.append(
                f"  FK: {fk['from_column']} -> {fk['to_table']}.{fk['to_column']}"
            )
        if table.get("sample_rows"):
            lines.append(f"  Sample rows ({len(table['sample_rows'])}):")
            header = " | ".join(str(c) for c in table["sample_columns"])
            lines.append(f"    {header}")
            for row in table["sample_rows"]:
                vals = " | ".join(str(v) for v in row)
                lines.append(f"    {vals}")
        lines.append("")

    shape = context["output_shape"]
    lines.append(
        f"Expected output: {shape['columns']} column(s), {shape['rows']} row(s)"
    )
    return "\n".join(lines)
