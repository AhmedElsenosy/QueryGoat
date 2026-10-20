"""Gmail-only puzzle announcement emails.

Uses the stdlib SMTP client with the Gmail SMTP server and an app password
from settings.  Emails are best-effort: individual recipient failures are
logged and reported, never raised, so notifications can never break the
daily publish pipeline.
"""

from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage
from socket import gaierror, timeout as socket_timeout
from typing import Iterable

from app.config import settings

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587  # STARTTLS
SMTP_TIMEOUT_S = 30.0
RECIPIENT_DELAY_S = 0.1
GMAIL_DAILY_LIMIT = 450


def email_configured() -> bool:
    return bool(settings.email_address and settings.email_password)


def puzzle_announcement_email(
    *,
    puzzle_date: str,
    prompt: str,
    difficulty: str,
    database: str,
    columns: int,
    rows: int,
) -> tuple[str, str]:
    """Return ``(subject, body)`` for the daily announcement."""
    subject = (
        f"QueryGoat {puzzle_date}: today's puzzle is live ({difficulty} — {database})"
    )
    solve_url = settings.app_frontend_url.rstrip("/")
    body = (
        "A new SQL puzzle just went live.\n"
        "\n"
        f"{prompt}\n"
        "\n"
        f"Database: {database} ({difficulty})\n"
        f"Expected output: {columns} column(s) x {rows} row(s)\n"
        "\n"
        f"Solve it now: {solve_url}\n"
        "\n"
        "Your streak resets if you miss a day. Good luck.\n"
        "\n"
        "— QueryGoat\n"
    )
    return subject, body


def send_puzzle_announcement(
    recipients: Iterable[str],
    subject: str,
    body: str,
) -> dict[str, object]:
    """Send one email per recipient over a single SMTP connection.

    Never raises for recipient failures; returns counts so the caller can
    decide whether to stamp ``notified_at``.
    """
    sender = settings.email_address
    sent = 0
    failed: list[str] = []

    if not email_configured():
        log.warning("Email not configured (EMAIL_ADDRESS/EMAIL_PASSWORD), skipping.")
        return {"sent": sent, "failed": list(recipients), "configured": False}

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_S) as smtp:
            smtp.starttls()
            smtp.login(sender, settings.email_password)
            for recipient in recipients:
                if sent >= GMAIL_DAILY_LIMIT:
                    log.warning(
                        "Gmail daily cap reached, stopping after %d sends.", sent
                    )
                    break
                message = EmailMessage()
                message["From"] = f"QueryGoat <{sender}>"
                message["To"] = recipient
                message["Subject"] = subject
                message.set_content(body)
                try:
                    smtp.send_message(message)
                    sent += 1
                except smtplib.SMTPRecipientsRefused:
                    log.warning("SMTP refused recipient: %s", recipient)
                    failed.append(recipient)
                time.sleep(RECIPIENT_DELAY_S)
    except (
        smtplib.SMTPAuthenticationError,
        smtplib.SMTPException,
        gaierror,
        socket_timeout,
        OSError,
    ) as exc:
        log.error("Puzzle announcement email failed: %s", exc)
        return {"sent": sent, "failed": failed, "configured": True, "error": str(exc)}

    return {"sent": sent, "failed": failed, "configured": True}
