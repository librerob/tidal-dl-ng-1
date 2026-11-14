from tidal_dl_ng.playlist_checkpoint import PlaylistCheckpoint


def test_checkpoint_preserves_retagged_files_and_retries_empty_files(tmp_path):
    checkpoint = PlaylistCheckpoint(tmp_path, ["playlist", "LOSSLESS"], ["one", "two"])
    track = tmp_path / "track.flac"
    track.write_bytes(b"complete")
    checkpoint.record(1, track)

    reopened = PlaylistCheckpoint(tmp_path, ["playlist", "LOSSLESS"], ["one", "two"])
    assert reopened.completed() == {1: track}
    assert PlaylistCheckpoint(tmp_path, ["playlist", "LOSSLESS"], ["two", "one"]).completed() == {}
    track.write_bytes(b"complete with new tags")
    assert reopened.completed() == {1: track}
    assert reopened.changed_files(tmp_path) == [track]
    track.write_bytes(b"")
    assert reopened.completed() == {}
    track.unlink()
    assert reopened.completed() == {}
