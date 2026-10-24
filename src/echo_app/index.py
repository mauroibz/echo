"""SQLite index of the library: a cache for fast listing and full-text search.

Everything here is derived from the recording folders. Deleting the file loses nothing;
``rebuild`` reconstructs it. A schema change simply drops and rebuilds.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .library import Library, Recording

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recordings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created TEXT NOT NULL,
    origin TEXT NOT NULL,
    state TEXT NOT NULL,
    duration REAL,
    transcript_status TEXT NOT NULL,
    edited INTEGER NOT NULL DEFAULT 0,
    folder_mtime REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
    id UNINDEXED, title, body, tokenize = 'unicode61 remove_diacritics 2'
);
"""


class Index:
    def __init__(self, library: Library):
        self.library = library
        self.path = library.data_dir / "library.sqlite"
        self.db = self._open()

    def _open(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            db.executescript("DROP TABLE IF EXISTS recordings; DROP TABLE IF EXISTS search;")
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        db.executescript(_SCHEMA)
        return db

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def _mtime(rec: Recording) -> float:
        # Folder mtime changes when files are added/removed; meta and edits are replaced via
        # rename, which also bumps the folder mtime.
        try:
            return rec.folder.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    def upsert(self, rec: Recording) -> None:
        m = rec.meta
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO recordings VALUES (?,?,?,?,?,?,?,?,?)",
                (m.id, m.title, m.created, m.origin, m.state, m.duration,
                 rec.transcript_status(), int(rec.is_edited()), self._mtime(rec)),
            )
            self.db.execute("DELETE FROM search WHERE id = ?", (m.id,))
            self.db.execute("INSERT INTO search (id, title, body) VALUES (?,?,?)",
                            (m.id, m.title, rec.text()))

    def remove(self, rid: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM recordings WHERE id = ?", (rid,))
            self.db.execute("DELETE FROM search WHERE id = ?", (rid,))

    def sync(self) -> int:
        """Bring the index up to date with the folders. Returns the number of rows changed."""
        known = {r["id"]: r["folder_mtime"] for r in self.db.execute("SELECT id, folder_mtime FROM recordings")}
        changed = 0
        seen = set()
        for rec in self.library.all():
            seen.add(rec.id)
            if known.get(rec.id) != self._mtime(rec):
                self.upsert(rec)
                changed += 1
        for rid in set(known) - seen:
            self.remove(rid)
            changed += 1
        return changed

    def rebuild(self) -> int:
        with self.db:
            self.db.execute("DELETE FROM recordings")
            self.db.execute("DELETE FROM search")
        return self.sync()

    def list(self, query: str = "") -> list[sqlite3.Row]:
        if query.strip():
            fts = " ".join(f'"{t.replace(chr(34), "")}"*' for t in query.split())
            return self.db.execute(
                "SELECT r.* FROM recordings r JOIN search s ON s.id = r.id "
                "WHERE search MATCH ? ORDER BY r.created DESC", (fts,)).fetchall()
        return self.db.execute("SELECT * FROM recordings ORDER BY created DESC").fetchall()
