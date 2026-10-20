import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool
    user: str
    database: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    gmail: str = Field(min_length=6, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# Puzzle schema / context models (LeetCode-style puzzle card)
# ---------------------------------------------------------------------------

class ColumnInfo(BaseModel):
    name: str
    type: str
    pk: bool = False


class ForeignKeyInfo(BaseModel):
    from_column: str
    to_table: str
    to_column: str


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo]
    foreign_keys: list[ForeignKeyInfo]
    sample_columns: list[str]
    sample_rows: list[list[Any]]


class OutputShape(BaseModel):
    columns: int
    rows: int


class DailyPuzzlePublic(BaseModel):
    puzzle_date: str
    prompt: str
    difficulty: str
    database: str
    schema_info: list[TableInfo]
    output_shape: OutputShape


class DailyRunResponse(BaseModel):
    status: str
    puzzle_date: str
    attempts: int
    daily_puzzle_id: uuid.UUID | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Submission / grading
# ---------------------------------------------------------------------------

class SubmitTodayRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=10_000)


class SubmitTodayResponse(BaseModel):
    is_correct: bool
    status: str  # "correct" | "wrong" | "sql_error" | "timeout" | "too_many_rows" | "cheat"
    message: str
    attempts: int
    solved: bool
    puzzle_date: str
    points: int = 0
    current_streak: int = 0
    total_points: int = 0
    badge: str | None = None
