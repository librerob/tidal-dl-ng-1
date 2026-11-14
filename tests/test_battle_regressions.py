import time
from threading import Event, Semaphore
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from requests import HTTPError, Response
from rich.progress import Progress

from tidal_dl_ng.config import Tidal
from tidal_dl_ng.download import Download
from tidal_dl_ng.rate_limit import RateLimit


def test_missing_last_segment_fails_merge(tmp_path):
    first = tmp_path / "first"
    first.write_bytes(b"first")
    segments = [SimpleNamespace(path_segment=first), SimpleNamespace(path_segment=tmp_path / "missing")]
    assert not Download._segments_merge(None, tmp_path / "output", segments)


def test_failed_login_validation_keeps_saved_token():
    client = object.__new__(Tidal)
    client.token_from_storage = True
    client.data = SimpleNamespace(token_type=None, access_token=None, refresh_token=None, expiry_time=0)
    response = Response()
    response.status_code = 503
    client.session = Mock()
    client.session.load_oauth_session.side_effect = HTTPError(response=response)
    client._remove_token = Mock()
    assert not client.login_token()
    client._remove_token.assert_not_called()


def test_media_429_updates_shared_cooldown(monkeypatch, tmp_path):
    download = object.__new__(Download)
    download.event_abort = Event()
    download.event_run = Event()
    download.event_run.set()
    download.transfer_slots = Semaphore(1)
    download.rate_limit = RateLimit(download.event_abort, SimpleNamespace(rate_limit_breaker_threshold=1))
    download.progress = Progress()
    task = download.progress.add_task("test", total=1)

    response = Response()
    response.status_code = 429
    response.headers["Retry-After"] = "180"
    transport = MagicMock()
    transport.return_value.__enter__.return_value.get.return_value.__enter__.return_value = response
    monkeypatch.setattr("tidal_dl_ng.download.requests.Session", transport)
    before = time.monotonic()
    output = download._download_segment("https://example.invalid/segment", tmp_path, None, task, True)
    assert not output.result
    assert output.error.response is response
    assert download.rate_limit.open
    assert download.rate_limit.until >= before + 180
