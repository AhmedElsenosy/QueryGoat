"""Gmail-only address validation.

Rejects non-Gmail providers. Treats dots, plus-tags, and googlemail.com
as the same mailbox so users cannot register aliases of an existing account.
"""

from __future__ import annotations

import re

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status

GMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})
_LOCAL_ALLOWED = re.compile(r"^[a-z0-9.]+(?:\+[a-z0-9._-]+)?$")


class GmailValidationError(ValueError):
    pass


def canonicalize_gmail(email: str) -> str:
    local, domain = email.strip().lower().split("@", 1)
    if domain == "googlemail.com":
        domain = "gmail.com"
    local = local.split("+", 1)[0].replace(".", "")
    return f"{local}@{domain}"


def validate_gmail(raw: str) -> tuple[str, str]:
    """Return (normalized_email, canonical_email) or raise GmailValidationError."""
    try:
        validated = validate_email(
            raw,
            check_deliverability=False,
            allow_smtputf8=False,
        )
    except EmailNotValidError as exc:
        raise GmailValidationError(str(exc)) from exc

    normalized = validated.normalized.lower()
    local, domain = normalized.split("@", 1)

    if domain not in GMAIL_DOMAINS:
        raise GmailValidationError("Email must be a Gmail address (@gmail.com).")

    if not _LOCAL_ALLOWED.match(local):
        raise GmailValidationError("Gmail address contains invalid characters.")

    if local.startswith(".") or local.endswith(".") or ".." in local.split("+", 1)[0]:
        raise GmailValidationError("Gmail address has an invalid local part.")

    canonical = canonicalize_gmail(normalized)
    canonical_local = canonical.split("@", 1)[0]
    if not re.fullmatch(r"[a-z0-9]{6,30}", canonical_local):
        raise GmailValidationError(
            "Gmail username must be 6-30 letters or digits (dots and plus-tags ignored)."
        )

    return normalized, canonical


def require_gmail(raw: str) -> tuple[str, str]:
    try:
        return validate_gmail(raw)
    except GmailValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
