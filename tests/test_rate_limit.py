import uuid

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

_PAYLOAD = {
    "username": "goatlimituser",
    "gmail": "goatlimituser@gmail.com",
    "password": "hammer-bill-grip9",
}


def test_register_login_limits(monkeypatch) -> None:
    # Re-enable the limiter just for this test (conftest disables it).
    from app.rate_limit import limiter

    limiter.enabled = True
    monkeypatch.setattr(settings, "rate_limit_register", "2/minute")
    monkeypatch.setattr(settings, "rate_limit_login", "2/minute")

    s = uuid.uuid4().hex[:6]
    # Register limit: 2 allowed, 3rd refused
    for i in range(2):
        ok = client.post("/auth/register", json={
            "username": f"goatlimit{s}{i}",
            "gmail": f"goatlimit{s}{i}@gmail.com",
            "password": "hammer-bill-grip9",
        })
        assert ok.status_code == 201, ok.text
    third = client.post("/auth/register", json={
        "username": f"goatlimit{s}x",
        "gmail": f"goatlimit{s}x@gmail.com",
        "password": "hammer-bill-grip9",
    })
    assert third.status_code == 429, third.text

    # Login limit: keyed independently
    for i in range(2):
        ok = client.post("/auth/login", json={
            "username": f"goatlimit{s}0",
            "password": "hammer-bill-grip9",
        })
        assert ok.status_code == 200, ok.text
    third_login = client.post("/auth/login", json={
        "username": f"goatlimit{s}0",
        "password": "hammer-bill-grip9",
    })
    assert third_login.status_code == 429, third_login.text

    limiter.enabled = False


def test_submit_limit_keyed_by_user(monkeypatch) -> None:
    from app.rate_limit import limiter

    limiter.enabled = True
    monkeypatch.setattr(settings, "rate_limit_register", "1000/minute")
    monkeypatch.setattr(settings, "rate_limit_login", "1000/minute")
    monkeypatch.setattr(settings, "rate_limit_submit", "2/minute")

    suffix = uuid.uuid4().hex[:8]
    reg = client.post("/auth/register", json={
        "username": f"goatlbsub{suffix}",
        "gmail": f"goatlbsub{suffix}@gmail.com",
        "password": "hammer-bill-grip9",
    })
    assert reg.status_code == 201, reg.text
    login = client.post("/auth/login", json={
        "username": f"goatlbsub{suffix}",
        "password": "hammer-bill-grip9",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # One user hammering the endpoint
    for _ in range(2):
        ok = client.post("/puzzles/today/submit", json={"sql": "SELECT 1"}, headers=headers)
        assert ok.status_code == 200, ok.text
    blocked = client.post("/puzzles/today/submit", json={"sql": "SELECT 1"}, headers=headers)
    assert blocked.status_code == 429

    # Second user is independent (keyed per user id)
    other_suffix = uuid.uuid4().hex[:8]
    reg2 = client.post("/auth/register", json={
        "username": f"goatlbother{other_suffix}",
        "gmail": f"goatlbother{other_suffix}@gmail.com",
        "password": "hammer-bill-grip9",
    })
    assert reg2.status_code == 201, reg2.text
    login2 = client.post("/auth/login", json={
        "username": f"goatlbother{other_suffix}",
        "password": "hammer-bill-grip9",
    })
    headers2 = {"Authorization": f"Bearer {login2.json()['access_token']}"}
    ok = client.post("/puzzles/today/submit", json={"sql": "SELECT 1"}, headers=headers2)
    assert ok.status_code == 200, ok.text

    limiter.enabled = False
