"""Rate limiting via slowapi.

Limit values are callables so limits are read from settings at request time
(test suites can tighten/loosen them dynamically without re-importing).
"""

from __future__ import annotations

import uuid
from typing import Any

import jwt as pyjwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address, headers_enabled=False)


def submit_key(request: Request) -> str:
    """Rate-limit key: user id when a valid access token is present, else IP."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header[len("Bearer ") :].strip()
        if token:
            try:
                payload = pyjwt.decode(
                    token,
                    settings.jwt_secret,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": False},
                )
                if payload.get("typ") == "access" and payload.get("sub"):
                    uuid.UUID(payload["sub"])
                    return f"user:{payload['sub']}"
            except Exception:
                pass
    return get_remote_address(request)
