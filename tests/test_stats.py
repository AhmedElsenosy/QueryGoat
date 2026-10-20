import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import User, UserStats
from app.services import stats as S

client = TestClient(app)


def _make_user() -> User:
    session = SessionLocal()
    try:
        user = User(
            username=f"goatstat{uuid.uuid4().hex[:8]}",
            email=f"goatstat{uuid.uuid4().hex[:8]}@gmail.com",
            email_canonical=f"goatstat{uuid.uuid4().hex[:8]}",
            password_hash="x",
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def _get_stats(user_id) -> UserStats:
    session = SessionLocal()
    try:
        return session.execute(
            select(UserStats).where(UserStats.user_id == user_id)
        ).scalar_one()
    finally:
        session.close()


def test_badge_thresholds() -> None:
    assert S.badge_for_points(0) is None
    assert S.badge_for_points(9) is None
    assert S.badge_for_points(10) == "Beginner"
    assert S.badge_for_points(24) == "Beginner"
    assert S.badge_for_points(25) == "Intermediate"
    assert S.badge_for_points(49) == "Intermediate"
    assert S.badge_for_points(50) == "Advanced"
    assert S.badge_for_points(99) == "Advanced"
    assert S.badge_for_points(100) == "GOAT"


def test_points_fall_out_with_difficulty() -> None:
    assert S.DIFFICULTY_POINTS == {"easy": 1, "medium": 2, "hard": 3, "extra": 4}


def test_first_solve_awards_points_and_starts_streak() -> None:
    user = _make_user()
    session = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()
        S.award_first_solve(session, user.id, "hard", today)
        session.commit()
    finally:
        session.close()

    stats = _get_stats(user.id)
    assert stats.total_points == 3
    assert stats.hard_solved == 1
    assert stats.current_streak == 1
    assert stats.longest_streak == 1


def test_consecutive_days_build_streak() -> None:
    user = _make_user()
    session = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        S.award_first_solve(session, user.id, "medium", yesterday)
        S.award_first_solve(session, user.id, "easy", today)
        session.commit()
    finally:
        session.close()

    stats = _get_stats(user.id)
    assert stats.total_points == 3  # medium=2 + easy=1
    assert stats.medium_solved == 1 and stats.easy_solved == 1
    assert stats.current_streak == 2
    assert stats.longest_streak == 2
    assert stats.last_daily_solved_date == datetime.now(timezone.utc).date()


def test_gap_resets_streak_but_keeps_longest() -> None:
    user = _make_user()
    session = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()
        far = today - timedelta(days=6)
        older = today - timedelta(days=7)
        S.award_first_solve(session, user.id, "medium", older)
        S.award_first_solve(session, user.id, "medium", far)
        S.award_first_solve(session, user.id, "medium", today)  # 3-day chain then gap
        session.commit()
    finally:
        session.close()

    stats = _get_stats(user.id)
    # older(-7)->far(-6) built a 2-day chain; today (5-day gap) restarted at 1
    assert stats.current_streak == 1
    assert stats.longest_streak == 2


def test_effective_streak_is_zero_when_dead() -> None:
    user = _make_user()
    session = SessionLocal()
    try:
        old = datetime.now(timezone.utc).date() - timedelta(days=3)
        S.award_first_solve(session, user.id, "medium", old)
        session.commit()
    finally:
        session.close()

    stats = _get_stats(user.id)
    today = datetime.now(timezone.utc).date()
    assert stats.current_streak == 1  # stored chain value
    assert S.effective_current_streak(stats, today) == 0  # display value


def test_submit_awards_points_and_stats_endpoint_tracks_them() -> None:
    from app.agent.run_daily import run_daily
    from app.models import DailyPuzzle
    from app.services.stats import DIFFICULTY_POINTS

    run_daily()
    session = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()
        puzzle = session.execute(
            select(DailyPuzzle).where(DailyPuzzle.puzzle_date == today)
        ).scalar_one()
        expected_points = DIFFICULTY_POINTS[puzzle.question.difficulty]
        gold = puzzle.question.gold_sql
    finally:
        session.close()

    suffix = uuid.uuid4().hex[:8]
    reg = client.post("/auth/register", json={
        "username": f"goatpts{suffix}",
        "gmail": f"goatpts{suffix}@gmail.com",
        "password": "hammer-bill-grip9",
    })
    assert reg.status_code == 201, reg.text
    login = client.post("/auth/login", json={
        "username": f"goatpts{suffix}",
        "password": "hammer-bill-grip9",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    submit = client.post("/puzzles/today/submit", json={"sql": gold}, headers=headers)
    assert submit.status_code == 200, submit.text
    body = submit.json()
    assert body["is_correct"] is True
    assert body["points"] == expected_points
    assert body["total_points"] == expected_points
    assert body["current_streak"] == 1
    assert body["badge"] is None or body["badge"] == "Beginner"

    # First-solve only: resubmitting awards nothing new
    again = client.post("/puzzles/today/submit", json={"sql": gold}, headers=headers)
    assert again.json()["points"] == 0
    assert again.json()["total_points"] == expected_points

    # /users/me/stats matches
    stats = client.get("/users/me/stats", headers=headers)
    st = stats.json()
    assert st["points"] == expected_points
    assert st["total_solved"] == 1
    assert st["current_streak"] == 1
    assert st["last_daily_solved_date"] == datetime.now(timezone.utc).date().isoformat()


def test_me_stats_endpoint() -> None:
    suffix = uuid.uuid4().hex[:8]
    reg = client.post("/auth/register", json={
        "username": f"goatme{suffix}",
        "gmail": f"goatme{suffix}@gmail.com",
        "password": "hammer-bill-grip9",
    })
    assert reg.status_code == 201, reg.text
    login = client.post("/auth/login", json={
        "username": f"goatme{suffix}",
        "password": "hammer-bill-grip9",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/users/me/stats", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["points"] == 0
    assert body["badge"] is None
    assert body["current_streak"] == 0
    assert body["total_solved"] == 0

    unauth = client.get("/users/me/stats")
    assert unauth.status_code == 401
