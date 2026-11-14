import json
import sqlite3
from contextlib import closing
from hashlib import sha256
from pathlib import Path


class PlaylistCheckpoint:
    """Record completed files for an exact playlist snapshot."""

    def __init__(self, directory: Path, options: list[str], media_ids: list[str]):
        directory.mkdir(parents=True, exist_ok=True)
        self.database = directory / ".tidal-downloads.sqlite3"
        payload = json.dumps([options, media_ids]).encode()
        self.snapshot = sha256(payload).hexdigest()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS complete (
                    snapshot TEXT NOT NULL, position INTEGER NOT NULL, path TEXT NOT NULL,
                    size INTEGER NOT NULL, mtime INTEGER NOT NULL,
                    PRIMARY KEY (snapshot, position)
                )"""
            )

    def completed(self) -> dict[int, Path]:
        with closing(sqlite3.connect(self.database)) as db:
            entries = db.execute(
                "SELECT position, path FROM complete WHERE snapshot = ?", (self.snapshot,)
            ).fetchall()
        result = {}
        for position, filename in entries:
            path = Path(filename)
            try:
                current = path.stat()
                if path.is_file() and current.st_size > 0:
                    result[position] = path
            except OSError:
                continue
        return result

    def recorded_positions(self) -> set[int]:
        with closing(sqlite3.connect(self.database)) as db:
            rows = db.execute("SELECT position FROM complete WHERE snapshot = ?", (self.snapshot,))
            return {position for (position,) in rows}

    def record(self, position: int, path: Path):
        try:
            current = path.stat()
        except OSError:
            return
        if not path.is_file() or not current.st_size:
            return
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO complete VALUES (?, ?, ?, ?, ?)",
                (self.snapshot, position, str(path), current.st_size, current.st_mtime_ns),
            )

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
