import pytest

from app import emailer as _emailer
from app.rate_limit import limiter as _limiter

_REAL_SEND = _emailer.send_puzzle_announcement
_FAKE_CALLS: list[dict] = []


@pytest.fixture(autouse=True)
def _no_real_emails(monkeypatch):
    """Never let pytest hit the real Gmail SMTP server."""
    _FAKE_CALLS.clear()

    def _fake(recipients, subject, body):
        _FAKE_CALLS.append(
            {"recipients": list(recipients), "subject": subject, "body": body}
        )
        return {"sent": len(list(recipients)), "failed": [], "configured": True}

    monkeypatch.setattr(_emailer, "send_puzzle_announcement", _fake)


@pytest.fixture(autouse=True)
def _no_rate_limits():
    """Rate limiting off unless a dedicated test opts in."""
    _limiter.enabled = False
    yield
    _limiter.enabled = True


@pytest.fixture()
def real_emailer(monkeypatch):
    """Opt back into the real SMTP implementation (unit tests with fakes)."""
    monkeypatch.setattr(_emailer, "send_puzzle_announcement", _REAL_SEND)
    return _emailer


def fake_email_calls():
    from app import emailer as _e

    return _FAKE_CALLS
