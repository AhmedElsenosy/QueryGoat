import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.google_oauth import create_oauth_state

client = TestClient(app)


def test_google_login_requires_config() -> None:
    response = client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 503


def test_google_callback_creates_user_and_tokens() -> None:
    suffix = uuid.uuid4().hex[:10]
    email = f"oauthgoat{suffix}@gmail.com"
    state = create_oauth_state()

    token_json = MagicMock()
    token_json.status_code = 200
    token_json.json.return_value = {"access_token": "ya29.fake"}

    userinfo_json = MagicMock()
    userinfo_json.status_code = 200
    userinfo_json.json.return_value = {
        "sub": f"google-sub-{suffix}",
        "email": email,
        "email_verified": True,
    }

    mock_http = MagicMock()
    mock_http.__enter__.return_value = mock_http
    mock_http.__exit__.return_value = False
    mock_http.post.return_value = token_json
    mock_http.get.return_value = userinfo_json

    from app.config import settings as app_settings

    with (
        patch.object(app_settings, "google_client_id", "test-client-id"),
        patch.object(app_settings, "google_client_secret", "test-client-secret"),
        patch("app.services.google_oauth.httpx.Client", return_value=mock_http),
    ):
        response = client.get(
            "/auth/google/callback",
            params={"code": "fake-code", "state": state},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"].endswith("@gmail.com")
