from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rich.progress import Progress

from tidal_dl_ng.config import Tidal
from tidal_dl_ng.download import Download


def test_logout_removes_keyring_entry_even_when_disabled(monkeypatch, tmp_path):
    client = object.__new__(Tidal)
    client.file_path = tmp_path / "token.json"
    client.file_path.write_text("{}", encoding="utf-8")
    client.settings = SimpleNamespace(data=SimpleNamespace(use_keyring=False))
    backend = Mock()
    monkeypatch.setattr("tidal_dl_ng.config.import_module", lambda _: backend)
    assert client._remove_token()
    assert not client.file_path.exists()
    backend.delete_password.assert_called_once()


def test_keyring_error_still_removes_file(monkeypatch, tmp_path):
    client = object.__new__(Tidal)
    client.file_path = tmp_path / "token.json"
    client.file_path.write_text("{}", encoding="utf-8")
    backend = Mock()
    backend.get_password.side_effect = RuntimeError
    monkeypatch.setattr(client, "_keyring", lambda **_: backend)
    with pytest.warns(RuntimeWarning, match="OS keyring"):
        assert not client._remove_token()
    assert not client.file_path.exists()


def test_playlist_stops_scheduling_when_breaker_opens():
    download = object.__new__(Download)
    download.settings = SimpleNamespace(data=SimpleNamespace(downloads_concurrent_max=1))
    download.event_abort = Mock()
    download.event_abort.is_set.return_value = False
    download.rate_limit = SimpleNamespace(open=False)
    attempted = []

    def item(media):
        attempted.append(media)
        download.rate_limit.open = True
        return False, ""

    download.item = item
    progress = Progress()
    tracks = ["one", "two", "three"]
    task = progress.add_task("playlist", total=len(tracks))
    assert download._run_playlist(tracks, progress, task, {}, True, {}) == 1
    assert attempted == ["one"]
    assert progress.tasks[task].completed == 1
