import smtplib
from email.message import EmailMessage

import pytest

from app import emailer
from app.config import settings


class _FakeSMTP:
    """Stands in for smtplib.SMTP; records everything."""
    connections: list["_FakeSMTP"] = []
    refused: set[str] = set()
    fail_login: bool = False

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.logins: list[tuple[str, str]] = []
        self.messages: list[EmailMessage] = []
        self.logged_in = False
        _FakeSMTP.connections.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, password):
        if _FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad password")
        self.logins.append((user, password))

    def send_message(self, message: EmailMessage):
        recipient = message["To"]
        if recipient in _FakeSMTP.refused:
            raise smtplib.SMTPRecipientsRefused({recipient: (550, b"no such user")})
        self.messages.append(message)


@pytest.fixture()
def fake_smtp(monkeypatch):
    _FakeSMTP.connections.clear()
    _FakeSMTP.refused.clear()
    _FakeSMTP.fail_login = False
    monkeypatch.setattr(emailer.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(emailer.time, "sleep", lambda *_: None)
    return _FakeSMTP


def test_announcement_content():
    subject, body = emailer.puzzle_announcement_email(
        puzzle_date="2026-10-20",
        prompt="What is the average unit price of tracks that belong to Jazz genre?",
        difficulty="medium",
        database="Chinook",
        columns=1,
        rows=1,
    )
    assert "medium" in subject and "Chinook" in subject
    assert "Jazz genre" in body
    assert "1 column(s) x 1 row(s)" in body
    assert settings.app_frontend_url.rstrip("/") in body


def test_one_message_per_recipient(fake_smtp, real_emailer):
    result = emailer.send_puzzle_announcement(
        ["a@gmail.com", "b@gmail.com", "c@gmail.com"], "Subject", "Body"
    )
    assert result["sent"] == 3 and result["failed"] == []


def test_refused_recipients_are_counted(fake_smtp, real_emailer):
    _FakeSMTP.refused.add("b@gmail.com")
    result = emailer.send_puzzle_announcement(
        ["a@gmail.com", "b@gmail.com"], "S", "B"
    )
    assert result["sent"] == 1
    assert result["failed"] == ["b@gmail.com"]


def test_bad_password_reports_error_not_raise(fake_smtp, real_emailer):
    _FakeSMTP.fail_login = True
    result = emailer.send_puzzle_announcement(["a@gmail.com"], "S", "B")
    assert result["sent"] == 0
    assert result.get("error") is not None


def test_unconfigured_skips_gracefully(monkeypatch, fake_smtp, real_emailer):
    monkeypatch.setattr(emailer.settings, "email_address", "")
    monkeypatch.setattr(emailer.settings, "email_password", "")
    result = emailer.send_puzzle_announcement(["a@gmail.com"], "S", "B")
    assert result["configured"] is False
    assert not _FakeSMTP.connections
