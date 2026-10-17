"""APPROVE_PASSCODE on the approve route: checked before any approval token is minted."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from lore.api import app as api
from lore.api.ratelimit import RateLimiter


def _req(ip: str) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=ip))


@pytest.fixture
def passcode(monkeypatch):
    monkeypatch.setattr(api.settings, "approve_passcode", "open-sesame")
    monkeypatch.setattr(api, "passcode_failures", RateLimiter(5, 20))


def test_right_passcode_passes(passcode):
    api._check_passcode("open-sesame", _req("1.1.1.1"))


def test_wrong_passcode_is_refused_then_rate_limited(passcode):
    for _ in range(5):
        with pytest.raises(HTTPException) as e:
            api._check_passcode("guess", _req("2.2.2.2"))
        assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:  # 6th try, even with the right passcode: locked out
        api._check_passcode("open-sesame", _req("2.2.2.2"))
    assert e.value.status_code == 429
    api._check_passcode("open-sesame", _req("3.3.3.3"))  # other clients aren't affected


def test_no_passcode_configured_refuses_everything(monkeypatch):
    monkeypatch.setattr(api.settings, "approve_passcode", "")
    with pytest.raises(HTTPException) as e:
        api._check_passcode("", _req("4.4.4.4"))
    assert e.value.status_code == 503


def test_blocked_records_nothing():
    rl = RateLimiter(2, 10)
    assert rl.blocked("k", now=100) == 0
    rl.check("k", now=100)
    rl.check("k", now=101)
    assert rl.blocked("k", now=102) > 0
    assert rl.blocked("k", now=170) == 0
