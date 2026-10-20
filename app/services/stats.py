"""Points, streaks and badges.

All day math is UTC, matching how daily puzzles publish (UTC midnight).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User as User
from app.models import UserStats

log = logging.getLogger(__name__)

DIFFICULTY_POINTS = {
    "easy": 1,
    "medium": 2,
    "hard": 3,
    "extra": 4,
}

BADGES: list[tuple[int, str]] = [
    (100, "GOAT"),
    (50, "Advanced"),
    (25, "Intermediate"),
    (10, "Beginner"),
]

_MIN_BADGE_POINTS = BADGES[-1][0]


def badge_for_points(points: int) -> str | None:
    if points < _MIN_BADGE_POINTS:
        return None
    for threshold, name in BADGES:
        if points >= threshold:
            return name
    return None


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def is_streak_alive(stats: UserStats | None, today: date) -> bool:
    """Streak counts as alive if the user solved today or yesterday (UTC)."""
    if stats is None or stats.last_daily_solved_date is None:
        return False
    last = stats.last_daily_solved_date
    return last in (today, today - timedelta(days=1))


def effective_current_streak(stats: UserStats | None, today: date) -> int:
    if not is_streak_alive(stats, today):
        return 0
    return stats.current_streak


def get_or_create_stats(db: Session, user_id) -> UserStats:
    stats = db.execute(
        select(UserStats).where(UserStats.user_id == user_id)
    ).scalar_one_or_none()
    if stats is None:
        stats = UserStats(user_id=user_id)
        db.add(stats)
        db.flush()
    return stats


def update_streak_on_solve(stats: UserStats, puzzle_date: date) -> None:
    """Chain the streak on a first daily solve. Mutates in place."""
    last = stats.last_daily_solved_date
    if last == puzzle_date:
        # Concurrent first-solve already landed; nothing to do.
        return
    if last is not None and last == puzzle_date - timedelta(days=1):
        stats.current_streak += 1
    else:
        stats.current_streak = 1
    stats.longest_streak = max(stats.longest_streak, stats.current_streak)
    stats.last_daily_solved_date = puzzle_date


def award_first_solve(
    db: Session, user_id, question_difficulty: str, puzzle_date: date
) -> UserStats:
    """Award points + streak for a first daily solve.

    Must be called in the same transaction/integrity window as the
    ``Submission`` insert so a lost race over the partial unique
    ``(user_id, question_id) WHERE is_correct`` index rolls this back too.
    """
    stats = get_or_create_stats(db, user_id)
    points = DIFFICULTY_POINTS.get(question_difficulty, 0)
    stats.total_points += points
    solved_col = f"{question_difficulty}_solved"
    if hasattr(stats, solved_col):
        setattr(stats, solved_col, getattr(stats, solved_col) + 1)
    update_streak_on_solve(stats, puzzle_date)
    return stats


def total_solved(stats: UserStats | None) -> int:
    if stats is None:
        return 0
    return (
        stats.easy_solved
        + stats.medium_solved
        + stats.hard_solved
        + stats.extra_solved
    )


def leaderboard_order():
    """ORDER BY expressions: points first, longest streak as tie-break."""
    from sqlalchemy import desc, func

    return (
        desc(func.coalesce(UserStats.total_points, 0)),
        desc(func.coalesce(UserStats.longest_streak, 0)),
    )


def rank_of(user_id) :
    """Subquery SELECT: the caller's 1-based rank among active users."""
    from sqlalchemy import func, select

    my_points = (
        select(func.coalesce(UserStats.total_points, 0))
        .where(UserStats.user_id == user_id)
        .scalar_subquery()
    )
    ahead = (
        select(func.count())
        .select_from(User)
        .outerjoin(UserStats, UserStats.user_id == User.id)
        .where(
            User.is_active.is_(True),
            func.coalesce(UserStats.total_points, 0) > my_points,
        )
        .scalar_subquery()
    )
    return ahead + 1
