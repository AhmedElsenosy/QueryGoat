from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.gmail import require_gmail
from app.models import RefreshToken, User
from app.schemas import TokenResponse
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def _username_taken(db: Session, username: str) -> bool:
    stmt = select(User.id).where(func.lower(User.username) == username.lower())
    return db.execute(stmt).scalar_one_or_none() is not None


def register_user(db: Session, username: str, gmail: str, password: str) -> User:
    email, email_canonical = require_gmail(gmail)
    username_norm = username.lower()

    if _username_taken(db, username_norm):
        raise ValueError("Username is already taken.")

    existing_email = db.execute(
        select(User.id).where(User.email_canonical == email_canonical)
    ).scalar_one_or_none()
    if existing_email is not None:
        raise ValueError("This Gmail address is already registered.")

    user = User(
        username=username_norm,
        email=email,
        email_canonical=email_canonical,
        password_hash=hash_password(password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Username or Gmail is already registered.") from exc
    db.refresh(user)
    return user


def _username_from_gmail(db: Session, canonical_email: str) -> str:
    base = canonical_email.split("@", 1)[0][:24]
    if not _username_taken(db, base):
        return base
    for _ in range(8):
        candidate = f"{base}_{uuid.uuid4().hex[:6]}"
        if not _username_taken(db, candidate):
            return candidate
    raise ValueError("Could not allocate a username.")


def login_or_register_google(db: Session, *, google_sub: str, email: str) -> User:
    email_norm, canonical = require_gmail(email)

    by_sub = db.execute(
        select(User).where(User.google_sub == google_sub)
    ).scalar_one_or_none()
    if by_sub is not None:
        return by_sub

    by_email = db.execute(
        select(User).where(User.email_canonical == canonical)
    ).scalar_one_or_none()
    if by_email is not None:
        if by_email.google_sub and by_email.google_sub != google_sub:
            raise ValueError("This Gmail is already linked to another Google account.")
        by_email.google_sub = google_sub
        db.commit()
        db.refresh(by_email)
        return by_email

    user = User(
        username=_username_from_gmail(db, canonical),
        email=email_norm,
        email_canonical=canonical,
        password_hash=None,
        google_sub=google_sub,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Could not create Google account.") from exc
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not user.password_hash or not verify_password(user.password_hash, password):
        return None
    return user


def issue_tokens(db: Session, user: User) -> TokenResponse:
    jti = uuid.uuid4().hex
    access = create_access_token(user.id)
    refresh, expires_at = create_refresh_token(user.id, jti)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            expires_at=expires_at,
        )
    )
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def rotate_refresh_token(db: Session, refresh_token: str) -> TokenResponse:
    payload = decode_token(refresh_token, expected_type="refresh")
    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not jti or not user_id:
        raise ValueError("Invalid refresh token.")

    stored = db.execute(
        select(RefreshToken).where(RefreshToken.jti == jti)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if (
        stored is None
        or stored.revoked_at is not None
        or stored.expires_at <= now
        or str(stored.user_id) != user_id
    ):
        raise ValueError("Invalid or expired refresh token.")

    stored.revoked_at = now
    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        db.commit()
        raise ValueError("Invalid or expired refresh token.")

    tokens = issue_tokens(db, user)
    return tokens
