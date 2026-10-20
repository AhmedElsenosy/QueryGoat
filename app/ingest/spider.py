from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SRC_DIR, settings
from app.db import SessionLocal, init_db
from app.ingest.curated import CURATED_DATABASES, DAILY_DIFFICULTIES, MAX_DAILY_ROWS
from app.ingest.filters import classify_difficulty, is_select_star, normalize_sql
from app.models import PuzzleDatabase, Question
from app.sandbox import (
    SQLExecutionError,
    UnsafeSQLError,
    copy_sqlite,
    execute_readonly,
    fingerprint,
    has_order_by,
)

REPO_ROOT = SRC_DIR.parents[2]
SPIDER_ROOT = REPO_ROOT / "spider"
SPLIT_FILES = {
    "train": SPIDER_ROOT / "train_spider.json",
    "dev": SPIDER_ROOT / "dev.json",
}


def _load_spider_examples() -> list[dict]:
    examples: list[dict] = []
    for split, path in SPLIT_FILES.items():
        with path.open() as handle:
            rows = json.load(handle)
        for row in rows:
            if row["db_id"] not in CURATED_DATABASES:
                continue
            examples.append(
                {
                    "db_id": row["db_id"],
                    "question": row["question"].strip(),
                    "query": row["query"].strip(),
                    "split": split,
                }
            )
    return examples


def _dedupe(examples: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for example in examples:
        key = (example["db_id"], normalize_sql(example["query"]))
        if key in seen:
            continue
        seen.add(key)
        unique.append(example)
    return unique


def _ensure_sqlite_copy(spider_db_id: str) -> Path:
    src = SPIDER_ROOT / "database" / spider_db_id / f"{spider_db_id}.sqlite"
    if not src.is_file():
        raise FileNotFoundError(f"Missing Spider sqlite: {src}")
    dest = settings.sqlite_data_dir / f"{spider_db_id}.sqlite"
    if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
        copy_sqlite(src, dest)
    return dest


def _upsert_database(db: Session, spider_db_id: str, sqlite_path: Path) -> PuzzleDatabase:
    rel_path = str(sqlite_path.relative_to(SRC_DIR))
    existing = db.execute(
        select(PuzzleDatabase).where(PuzzleDatabase.spider_db_id == spider_db_id)
    ).scalar_one_or_none()
    if existing is None:
        existing = PuzzleDatabase(
            spider_db_id=spider_db_id,
            display_name=CURATED_DATABASES[spider_db_id],
            sqlite_path=rel_path,
            is_active=True,
        )
        db.add(existing)
        db.flush()
        return existing
    existing.display_name = CURATED_DATABASES[spider_db_id]
    existing.sqlite_path = rel_path
    existing.is_active = True
    return existing


def ingest_spider(*, daily_only: bool = True) -> dict[str, int]:
    init_db()
    examples = _dedupe(_load_spider_examples())
    stats: Counter[str] = Counter()
    session = SessionLocal()
    try:
        db_rows: dict[str, PuzzleDatabase] = {}
        for spider_db_id in CURATED_DATABASES:
            sqlite_path = _ensure_sqlite_copy(spider_db_id)
            db_rows[spider_db_id] = _upsert_database(session, spider_db_id, sqlite_path)
        session.commit()

        for example in examples:
            stats["candidates"] += 1
            sql = example["query"]
            if is_select_star(sql):
                stats["select_star"] += 1
                continue
            difficulty = classify_difficulty(sql)
            if daily_only and difficulty not in DAILY_DIFFICULTIES:
                stats[f"skip_{difficulty}"] += 1
                continue
            sqlite_path = settings.sqlite_data_dir / f"{example['db_id']}.sqlite"
            try:
                result = execute_readonly(
                    sqlite_path,
                    sql,
                    timeout_s=2.0,
                    max_rows=MAX_DAILY_ROWS,
                )
            except (UnsafeSQLError, SQLExecutionError):
                stats["exec_error"] += 1
                continue
            if result.truncated or len(result.rows) == 0:
                stats["bad_row_count"] += 1
                continue
            if len(result.rows) > MAX_DAILY_ROWS:
                stats["too_many_rows"] += 1
                continue

            database = db_rows[example["db_id"]]
            normalized = normalize_sql(sql)
            already = session.execute(
                select(Question.id).where(
                    Question.database_id == database.id,
                    Question.gold_sql_normalized == normalized,
                )
            ).scalar_one_or_none()
            if already is not None:
                stats["duplicate"] += 1
                continue

            ordered = has_order_by(sql)
            session.add(
                Question(
                    database_id=database.id,
                    prompt=example["question"],
                    gold_sql=sql,
                    gold_sql_normalized=normalized,
                    difficulty=difficulty,
                    eligible_for_daily=difficulty in DAILY_DIFFICULTIES,
                    result_hash=fingerprint(
                        result.columns, result.rows, ordered=ordered
                    ),
                    result_row_count=len(result.rows),
                    result_col_count=len(result.columns),
                    result_ordered=ordered,
                    source="spider",
                    spider_split=example["split"],
                )
            )
            stats["inserted"] += 1
            stats[f"inserted_{difficulty}"] += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return dict(stats)


def main() -> None:
    stats = ingest_spider(daily_only=True)
    print("Spider ingest complete:", stats)


if __name__ == "__main__":
    main()
