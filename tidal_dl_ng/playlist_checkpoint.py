from tidal_dl_ng.playlist_checkpoint import PlaylistCheckpoint


def test_checkpoint_reopens_and_rejects_changed_files(tmp_path):
    checkpoint = PlaylistCheckpoint(tmp_path, ["playlist", "LOSSLESS"], ["one", "two"])
    track = tmp_path / "track.flac"
    track.write_bytes(b"complete")
    checkpoint.record(1, track)

    reopened = PlaylistCheckpoint(tmp_path, ["playlist", "LOSSLESS"], ["one", "two"])
    assert reopened.completed() == {1: track}
    assert PlaylistCheckpoint(tmp_path, ["playlist", "LOSSLESS"], ["two", "one"]).completed() == {}
    track.write_bytes(b"x")
    assert reopened.completed() == {}

    @staticmethod
    def changed_files(directory: Path) -> list[Path] | None:
        database = directory / ".tidal-downloads.sqlite3"
        if not database.is_file():
            return None
        with closing(sqlite3.connect(database)) as db:
            entries = db.execute("SELECT path, size, mtime FROM complete ORDER BY rowid").fetchall()
        latest = {filename: (size, mtime) for filename, size, mtime in entries}
        changed = []
        for filename, expected in latest.items():
            path = Path(filename)
            try:
                current = path.stat()
                if path.is_file() and (current.st_size, current.st_mtime_ns) == expected:
                    continue
            except OSError:
                pass
            changed.append(path)
        return changed
