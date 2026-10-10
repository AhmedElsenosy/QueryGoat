from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_db() -> dict[str, str | bool]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        row = conn.execute(text("SELECT current_user, current_database()")).one()
    return {"ok": True, "user": row[0], "database": row[1]}
