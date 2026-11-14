from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tidalapi.exceptions import TooManyRequests

from tidal_dl_ng import rate_limit
from tidal_dl_ng.rate_limit import DownloadStopped, RateLimit, retry_after


def make_limit(monkeypatch):
    now = [0.0]
    abort = Event()
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])

    def advance(seconds):
        now[0] += seconds

    monkeypatch.setattr(abort, "wait", advance)
    settings = SimpleNamespace(rate_limit_attempts=5, rate_limit_breaker_threshold=3)
    return RateLimit(abort, settings), now


def test_retries_after_server_delay(monkeypatch):
    limit, now = make_limit(monkeypatch)
    error = TooManyRequests()
    error.response = SimpleNamespace(headers={"Retry-After": "30"})
    operation = Mock(side_effect=[error, "stream"])
    assert retry_after(error) == 30
    assert limit.call(operation) == "stream"
    assert now[0] == 30
    assert limit.failures == 0


def test_breaker_stops_requests_until_resumed(monkeypatch):
    limit, _ = make_limit(monkeypatch)
    operation = Mock(side_effect=TooManyRequests)
    with pytest.raises(TooManyRequests):
        limit.call(operation)
    assert operation.call_count == 3
    with pytest.raises(DownloadStopped):
        limit.call(operation)
    assert operation.call_count == 3
    limit.resume()
    assert limit.call(lambda: "stream") == "stream"
