from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

from rich.progress import Progress
from tidalapi import Track

from tidal_dl_ng.download import Download


def test_single_file_transfers_without_head(tmp_path, monkeypatch):
    download = object.__new__(Download)
    download.event_abort = Event()
    download.rate_limit = SimpleNamespace(open=False)
    download.settings = SimpleNamespace(data=SimpleNamespace(downloads_simultaneous_per_track_max=1))
    download.progress = Progress()
    download.progress_gui = None
    download.fn_logger = Mock()
    monkeypatch.setattr("tidal_dl_ng.download.name_builder_item", lambda media: "fixture")
    head = Mock(side_effect=AssertionError("HEAD must not be required"))
    monkeypatch.setattr("tidal_dl_ng.download.requests.head", head)
    segment = tmp_path / "segment"
    segment.write_bytes(b"fixture")
    url = "https://example.invalid/audio"
    download._download_segment = Mock(return_value=SimpleNamespace(
        result=True, id_segment=0, path_segment=segment, url=url
    ))
    manifest = SimpleNamespace(get_urls=lambda: [url], is_encrypted=False)
    ok, path = download._download(object.__new__(Track), tmp_path / "audio", manifest)
    assert ok and path.read_bytes() == b"fixture"
    download._download_segment.assert_called_once()
    head.assert_not_called()


def test_bad_checkpoint_does_not_block_playlist_workers(tmp_path):
    from sqlite3 import DatabaseError

    download = object.__new__(Download)
    download.settings = SimpleNamespace(data=SimpleNamespace(downloads_concurrent_max=1))
    download.event_abort = Event()
    download.rate_limit = SimpleNamespace(open=False)
    download.fn_logger = Mock()
    checkpoint = Mock()
    checkpoint.completed.side_effect = DatabaseError("corrupt")
    path = tmp_path / "song"
    download.item = Mock(return_value=(True, path))
    progress = Progress()
    task = progress.add_task("playlist", total=1)
    results = {}
    assert download._run_playlist(["track"], progress, task, results, True, {}, checkpoint) == 1
    assert results == {0: path}
    download.item.assert_called_once_with(media="track")
    download.fn_logger.warning.assert_called_once()
