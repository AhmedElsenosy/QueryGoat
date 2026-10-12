import uuid

from fastapi.testclient import TestClient

from app.gmail import GmailValidationError, canonicalize_gmail, validate_gmail
from app.main import app

client = TestClient(app)


def _unique() -> str:
    return uuid.uuid4().hex[:10]


def test_gmail_rejects_non_gmail() -> None:
    for bad in (
        "user@yahoo.com",
        "user@outlook.com",
        "not-an-email",
        "a@gmail.com",
        "user@gmail.com.com",
    ):
        try:
            validate_gmail(bad)
            raise AssertionError(f"expected failure for {bad}")
        except GmailValidationError:
            pass


def test_gmail_accepts_and_canonicalizes() -> None:
    email, canonical = validate_gmail("John.Doe+tag@GoogleMail.com")
    assert email.endswith("@googlemail.com") or email.endswith("@gmail.com")
    assert canonical == "johndoe@gmail.com"
    assert canonicalize_gmail("john.doe@gmail.com") == "johndoe@gmail.com"


def test_register_and_login_flow() -> None:
    suffix = _unique()
    username = f"user_{suffix}"
    gmail = f"querygoat{suffix}@gmail.com"
    password = "correcthorse1"

    register = client.post(
        "/auth/register",
        json={"username": username, "gmail": gmail, "password": password},
    )
    assert register.status_code == 201, register.text
    body = register.json()
    assert body["username"] == username
    assert body["email"].endswith("@gmail.com")

    dup = client.post(
        "/auth/register",
        json={"username": username, "gmail": gmail, "password": password},
    )
    assert dup.status_code == 409

    alias = client.post(
        "/auth/register",
        json={
            "username": f"other_{suffix}",
            "gmail": f"query.goat{suffix}+alias@gmail.com",
            "password": password,
        },
    )
    assert alias.status_code == 409

    bad_login = client.post(
        "/auth/login",
        json={"username": username, "password": "wrongpass1"},
    )
    assert bad_login.status_code == 401

    login = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == username

    refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 200, refresh.text
    new_tokens = refresh.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    assert new_tokens["access_token"]

    reuse = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reuse.status_code == 401


def test_register_rejects_non_gmail() -> None:
    suffix = _unique()
    response = client.post(
        "/auth/register",
        json={
            "username": f"user_{suffix}",
            "gmail": f"user_{suffix}@yahoo.com",
            "password": "correcthorse1",
        },
    )
    assert response.status_code == 422
