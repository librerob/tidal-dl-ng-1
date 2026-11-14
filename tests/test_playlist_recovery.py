from threading import Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tidal_dl_ng.download import Download
from tidal_dl_ng.playlist_checkpoint import PlaylistCheckpoint


def test_track_quality_is_restored_after_error():
    download = object.__new__(Download)
    download.session = SimpleNamespace(audio_quality="HIGH")
    download.quality_lock = Lock()

    def request():
        assert download.session.audio_quality == "LOSSLESS"
        raise RuntimeError

    with pytest.raises(RuntimeError):
        download._track_stream(SimpleNamespace(get_stream=request), "LOSSLESS")
    assert download.session.audio_quality == "HIGH"


def test_playlist_uses_exact_paths_in_input_order(tmp_path):
    download = object.__new__(Download)
    download.fn_logger = Mock()
    first = tmp_path / "z.flac"
    second = tmp_path / "a.flac"
    unrelated = tmp_path / "unrelated.flac"
    for path in (second, first, unrelated):
        path.touch()
    (playlist,) = download.playlist_populate([first, second], "Test")
    assert playlist.read_text(encoding="utf-8").splitlines() == ["z.flac", "a.flac"]


def test_verify_files_reports_deleted_checkpoint_paths(tmp_path):
    checkpoint = PlaylistCheckpoint(tmp_path, ["test"], ["track"])
    file = tmp_path / "a.flac"
    file.write_bytes(b"media")
    checkpoint.record(0, file)
    assert checkpoint.changed_files(tmp_path) == []
    file.unlink()
    assert checkpoint.changed_files(tmp_path) == [file]
