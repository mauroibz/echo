"""SQLite index of the library: a cache for fast listing and full-text search.

Everything here is derived from the recording folders. Deleting the file loses nothing;
``rebuild`` reconstructs it. A schema change simply drops and rebuilds.
"""

from __future__ import annotations

import json
import sqlite3

from .library import Library, Recording, fold_tag

SCHEMA_VERSION = 3

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
CREATE TABLE IF NOT EXISTS tags (id TEXT NOT NULL, tag TEXT NOT NULL, tag_folded TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS tags_folded ON tags (tag_folded);
CREATE TABLE IF NOT EXISTS sets (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    members TEXT NOT NULL,  -- JSON list of the present members, in order
    newest TEXT NOT NULL  -- the newest member's created: where the set sits in the list
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
            db.executescript("DROP TABLE IF EXISTS recordings; DROP TABLE IF EXISTS search; "
                             "DROP TABLE IF EXISTS tags; DROP TABLE IF EXISTS sets;")
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
            body = "\n".join(p for p in (m.notes, rec.text()) if p)
            self.db.execute("INSERT INTO search (id, title, body) VALUES (?,?,?)", (m.id, m.title, body))
            self.db.execute("DELETE FROM tags WHERE id = ?", (m.id,))
            self.db.executemany("INSERT INTO tags (id, tag, tag_folded) VALUES (?,?,?)",
                                [(m.id, t, fold_tag(t)) for t in m.tags])

    def remove(self, rid: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM recordings WHERE id = ?", (rid,))
            self.db.execute("DELETE FROM search WHERE id = ?", (rid,))
            self.db.execute("DELETE FROM tags WHERE id = ?", (rid,))

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
        self._sync_sets()
        return changed

    def _sync_sets(self) -> None:
        """Set files are a handful of small files: read them all each time."""
        from . import sets

        created = {r["id"]: r["created"] for r in self.db.execute("SELECT id, created FROM recordings")}
        rows = []
        for s in sets.load_all(self.library):
            members = [m for m in s.members if m in created]
            if len(members) >= 2:
                rows.append((s.id, s.title, json.dumps(members), max(created[m] for m in members)))
        with self.db:
            self.db.execute("DELETE FROM sets")
            self.db.executemany("INSERT INTO sets VALUES (?,?,?,?)", rows)

    def sets(self) -> list[dict]:
        """Sets with two or more present members: {"id", "title", "members", "newest"}."""
        return [{"id": r["id"], "title": r["title"], "members": json.loads(r["members"]), "newest": r["newest"]}
                for r in self.db.execute("SELECT * FROM sets ORDER BY newest DESC")]

    def rebuild(self) -> int:
        with self.db:
            self.db.execute("DELETE FROM recordings")
            self.db.execute("DELETE FROM search")
            self.db.execute("DELETE FROM tags")
            self.db.execute("DELETE FROM sets")
        return self.sync()

    def list(self, query: str = "", tags=()) -> list[sqlite3.Row]:
        """Recordings matching the words of `query` (titles, notes, transcripts) and every tag;
        `#word` in the query is a tag too, and `#category:` any tag of that category."""
        words, tags = parse_query(query, tags)
        sql = "SELECT r.* FROM recordings r"
        args: list = []
        where = []
        if words:
            sql += " JOIN search s ON s.id = r.id"
            where.append("search MATCH ?")
            args.append(" ".join(f'"{w.replace(chr(34), "")}"*' for w in words))
        for t in tags:
            ft = fold_tag(t)
            if ft.endswith(":") and len(ft) > 1:  # "#client:": any value of the category
                where.append("r.id IN (SELECT id FROM tags WHERE substr(tag_folded, 1, ?) = ?)")
                args += [len(ft), ft]
            else:
                where.append("r.id IN (SELECT id FROM tags WHERE tag_folded = ?)")
                args.append(ft)
        if where:
            sql += " WHERE " + " AND ".join(where)
        return self.db.execute(sql + " ORDER BY r.created DESC", args).fetchall()

    def tag_counts(self) -> list[tuple[str, int]]:
        """(tag as most often typed, recordings) for every tag, most used first."""
        rows = self.db.execute("SELECT tag_folded, tag, COUNT(*) n FROM tags GROUP BY tag_folded, tag").fetchall()
        best: dict[str, tuple[str, int, int]] = {}  # folded -> (spelling, its count, total)
        for r in rows:
            spelling, n, total = best.get(r["tag_folded"], (r["tag"], 0, 0))
            if r["n"] > n:
                spelling, n = r["tag"], r["n"]
            best[r["tag_folded"]] = (spelling, n, total + r["n"])
        return sorted(((s, total) for s, _n, total in best.values()), key=lambda x: (-x[1], fold_tag(x[0])))


def parse_query(query: str, tags=()) -> tuple[list[str], list[str]]:
    """Split a search into words and tags ("#entrevista")."""
    words, out_tags = [], list(tags)
    for tok in query.split():
        if tok.startswith("#") and len(tok) > 1:
            out_tags.append(tok[1:])
        elif tok != "#":
            words.append(tok)
    return words, out_tags
