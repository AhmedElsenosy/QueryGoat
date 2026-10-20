import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email_canonical", name="uq_users_email_canonical"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    email_canonical: Mapped[str] = mapped_column(String(254), index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class PuzzleDatabase(Base):
    __tablename__ = "databases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    spider_db_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    sqlite_path: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    questions: Mapped[list["Question"]] = relationship(back_populates="database")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint(
            "database_id",
            "gold_sql_normalized",
            name="uq_questions_db_gold_sql",
        ),
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard', 'extra')",
            name="ck_questions_difficulty",
        ),
        CheckConstraint("result_row_count >= 1", name="ck_questions_row_count"),
        Index(
            "uq_questions_daily_date",
            "used_as_daily_on",
            unique=True,
            postgresql_where=text("used_as_daily_on IS NOT NULL"),
        ),
        Index(
            "ix_questions_daily_pool",
            "eligible_for_daily",
            "used_as_daily_on",
            "database_id",
            "difficulty",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    database_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("databases.id", ondelete="RESTRICT"),
        index=True,
    )
    prompt: Mapped[str] = mapped_column(Text)
    gold_sql: Mapped[str] = mapped_column(Text)
    gold_sql_normalized: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(16))
    eligible_for_daily: Mapped[bool] = mapped_column(Boolean, default=False)
    result_hash: Mapped[str] = mapped_column(String(64))
    result_row_count: Mapped[int] = mapped_column(Integer)
    result_ordered: Mapped[bool] = mapped_column(Boolean, default=False)
    rewritten_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_col_count: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(32), default="spider")
    spider_split: Mapped[str | None] = mapped_column(String(16), nullable=True)
    used_as_daily_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    database: Mapped[PuzzleDatabase] = relationship(back_populates="questions")
    daily_puzzles: Mapped[list["DailyPuzzle"]] = relationship(back_populates="question")


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'published', 'already_published', 'failed')",
            name="ck_agent_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    puzzle_date: Mapped[date] = mapped_column(Date, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="running")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    selected_question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    reject_reasons: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    daily_puzzles: Mapped[list["DailyPuzzle"]] = relationship(back_populates="agent_run")


class DailyPuzzle(Base):
    __tablename__ = "daily_puzzles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    puzzle_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="RESTRICT"),
        index=True,
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="RESTRICT"),
        index=True,
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    question: Mapped[Question] = relationship(back_populates="daily_puzzles")
    agent_run: Mapped[AgentRun] = relationship(back_populates="daily_puzzles")
