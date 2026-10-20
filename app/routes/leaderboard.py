from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_optional_user
from app.models import User, UserStats
from app.services import stats as stats_service

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: str
    points: int
    current_streak: int
    total_solved: int
    badge: str | None


class LeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]
    me: Optional[LeaderboardEntry] = None


def _entry(rank: int, user: User, stats_row: UserStats | None) -> LeaderboardEntry:
    points = stats_row.total_points if stats_row else 0
    today = stats_service.utc_today()
    return LeaderboardEntry(
        rank=rank,
        user_id=str(user.id),
        username=user.username,
        points=points,
        current_streak=stats_service.effective_current_streak(stats_row, today),
        total_solved=stats_service.total_solved(stats_row),
        badge=stats_service.badge_for_points(points),
    )


@router.get("", response_model=LeaderboardResponse)
def leaderboard(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> LeaderboardResponse:
    """Public global leaderboard, ordered by points (streak breaks ties)."""
    rows = db.execute(
        select(User, UserStats)
        .join(UserStats, UserStats.user_id == User.id, isouter=True)
        .where(User.is_active.is_(True))
        .order_by(
            *stats_service.leaderboard_order(),
            asc(User.created_at),
        )
        .limit(limit)
    ).all()

    entries = [_entry(rank, user, stats) for rank, (user, stats) in enumerate(rows, 1)]

    me = None
    if current_user is not None:
        for entry in entries:
            if entry.user_id == str(current_user.id):
                me = entry
                break
        else:
            paired = db.execute(
                select(User, UserStats)
                .join(UserStats, UserStats.user_id == User.id, isouter=True)
                .where(User.id == current_user.id)
            ).first()
            if paired is not None:
                rank = db.scalar(
                    select(stats_service.rank_of(current_user.id))
                )
                me = _entry(int(rank or 0), paired[0], paired[1])
    return LeaderboardResponse(entries=entries, me=me)
