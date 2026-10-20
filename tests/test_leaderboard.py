import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User, UserStats

client = TestClient(app)


def _make_user_with_points(points: int, longest: int) -> User:
    session = SessionLocal()
    try:
        user = User(
            username=f"goatlb{uuid.uuid4().hex[:8]}",
            email=f"goatlb{uuid.uuid4().hex[:8]}@gmail.com",
            email_canonical=f"goatlb{uuid.uuid4().hex[:8]}",
            password_hash="x",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(
            UserStats(
                user_id=user.id,
                total_points=points,
                longest_streak=longest,
                current_streak=longest,
                last_daily_solved_date=datetime.now(timezone.utc).date(),
                medium_solved=2 if points >= 2 else 0,
                easy_solved=max(0, points - 2),
            )
        )
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def test_leaderboard_orders_by_points_streak() -> None:
    top = _make_user_with_points(40, 1)
    streaky = _make_user_with_points(10, 7)
    low = _make_user_with_points(10, 2)

    response = client.get("/leaderboard")
    assert response.status_code == 200, response.text
    entries = response.json()["entries"]

    ids = [e["user_id"] for e in entries]
    assert ids.index(str(top.id)) < ids.index(str(streaky.id)) < ids.index(str(low.id))

    top_entry = entries[ids.index(str(top.id))]
    assert top_entry["points"] == 40
    assert top_entry["badge"] == "Intermediate"
    assert top_entry["rank"] >= 1

    streaky_entry = entries[ids.index(str(streaky.id))]
    assert streaky_entry["current_streak"] == 7
    assert streaky_entry["badge"] == "Beginner"
    low_entry = entries[ids.index(str(low.id))]
    assert low_entry["badge"] == "Beginner"


def test_leaderboard_includes_me_when_authed() -> None:
    response = client.get("/leaderboard")
    assert response.json()["me"] is None  # anonymous → no me block

    suffix = uuid.uuid4().hex[:8]
    reg = client.post("/auth/register", json={
        "username": f"goatmemaybe{suffix}",
        "gmail": f"goatmemaybe{suffix}@gmail.com",
        "password": "hammer-bill-grip9",
    })
    assert reg.status_code == 201, reg.text
    login = client.post("/auth/login", json={
        "username": f"goatmemaybe{suffix}",
        "password": "hammer-bill-grip9",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.get("/leaderboard", headers=headers)
    body = response.json()
    assert body["me"] is not None
    assert body["me"]["username"] == f"goatmemaybe{suffix}"
    assert body["me"]["rank"] >= 1
