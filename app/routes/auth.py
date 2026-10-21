from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.rate_limit import limiter
from app.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)
from app.services import auth as auth_service
from app.services import google_oauth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: settings.rate_limit_register)
def register(
    request: Request,
    body: RegisterRequest,
    db: Session = Depends(get_db),
) -> User:
    try:
        return auth_service.register_user(db, body.username, body.gmail, body.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post("/login", response_model=TokenResponse)
@limiter.limit(lambda: settings.rate_limit_login)
def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = auth_service.authenticate_user(db, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    return auth_service.issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(lambda: settings.rate_limit_refresh)
def refresh(
    request: Request,
    body: RefreshRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        return auth_service.rotate_refresh_token(db, body.refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/google/login")
def google_login() -> RedirectResponse:
    return RedirectResponse(google_oauth.google_authorization_url())


@router.get("/google/callback")
def google_callback(
    db: Session = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    # Hand the tokens back to the frontend through the URL fragment:
    # fragments are client-only (never sent to servers / logs).
    frontend = settings.app_frontend_url.rstrip("/")
    fail_url = f"{frontend}/auth/google/callback#"

    try:
        if error:
            raise ValueError(f"Google OAuth error: {error}")
        if not code or not state:
            raise ValueError("Missing Google OAuth code or state")
        google_oauth.verify_oauth_state(state)
        profile = google_oauth.exchange_code_for_google_user(code)
        user = auth_service.login_or_register_google(
            db,
            google_sub=profile["sub"],
            email=profile["email"],
        )
    except (ValueError, HTTPException) as exc:
        message = exc if isinstance(exc, ValueError) else str(exc.detail)
        return RedirectResponse(f"{fail_url}{urlencode({'oauth_error': message})}")

    tokens = auth_service.issue_tokens(db, user)
    return RedirectResponse(
        f"{frontend}/auth/google/callback"
        f"#access_token={tokens.access_token}&refresh_token={tokens.refresh_token}"
    )
