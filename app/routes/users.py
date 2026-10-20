from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User, UserStats
from app.services import stats as stats_service

router = APIRouter(prefix="/users", tags=["users"])


class UserStatsResponse(BaseModel):
    points: int
    badge: str | None
    current_streak: int
    longest_streak: int
    total_solved: int
    last_daily_solved_date: str | None
    easy_solved: int
    medium_solved: int
    hard_solved: int
    extra_solved: int


@router.get("/me/stats", response_model=UserStatsResponse)
def my_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserStatsResponse:
    stats_row = db.execute(
        select(UserStats).where(UserStats.user_id == current_user.id)
    ).scalar_one_or_none()
    today = datetime.now(timezone.utc).date()
    return UserStatsResponse(
        points=stats_row.total_points if stats_row else 0,
        badge=stats_service.badge_for_points(
            stats_row.total_points if stats_row else 0
        ),
        current_streak=stats_service.effective_current_streak(stats_row, today),
        longest_streak=stats_row.longest_streak if stats_row else 0,
        total_solved=stats_service.total_solved(stats_row),
        last_daily_solved_date=(
            stats_row.last_daily_solved_date.isoformat()
            if stats_row and stats_row.last_daily_solved_date
            else None
        ),
        easy_solved=stats_row.easy_solved if stats_row else 0,
        medium_solved=stats_row.medium_solved if stats_row else 0,
        hard_solved=stats_row.hard_solved if stats_row else 0,
        extra_solved=stats_row.extra_solved if stats_row else 0,
    )
