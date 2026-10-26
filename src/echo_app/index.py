"""SQLite index of the library: a cache for fast listing and full-text search.

Everything here is derived from the recording folders. Deleting the file loses nothing;
``rebuild`` reconstructs it. A schema change simply drops and rebuilds.
"""

from __future__ import annotations

import json
import re
import sqlite3

from .library import Library, Recording, fold_tag

SCHEMA_VERSION = 4

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
-- What each named speaker said in each recording, and who speaks where (search by speaker).
CREATE VIRTUAL TABLE IF NOT EXISTS spoken USING fts5(
    id UNINDEXED, person UNINDEXED, body, tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS speakers (
    id TEXT NOT NULL, number INTEGER NOT NULL, name TEXT NOT NULL, name_folded TEXT NOT NULL,
    seconds REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS speakers_folded ON speakers (name_folded);
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
                             "DROP TABLE IF EXISTS tags; DROP TABLE IF EXISTS sets; "
                             "DROP TABLE IF EXISTS spoken; DROP TABLE IF EXISTS speakers;")
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
            self.db.execute("DELETE FROM spoken WHERE id = ?", (m.id,))
            self.db.execute("DELETE FROM speakers WHERE id = ?", (m.id,))
            for number, (name, text, seconds) in _named_speech(rec).items():
                self.db.execute("INSERT INTO spoken (id, person, body) VALUES (?,?,?)", (m.id, fold_tag(name), text))
                self.db.execute("INSERT INTO speakers VALUES (?,?,?,?,?)",
                                (m.id, number, name, fold_tag(name), round(seconds, 1)))

    def remove(self, rid: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM recordings WHERE id = ?", (rid,))
            self.db.execute("DELETE FROM search WHERE id = ?", (rid,))
            self.db.execute("DELETE FROM tags WHERE id = ?", (rid,))
            self.db.execute("DELETE FROM spoken WHERE id = ?", (rid,))
            self.db.execute("DELETE FROM speakers WHERE id = ?", (rid,))

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
            self.db.execute("DELETE FROM spoken")
            self.db.execute("DELETE FROM speakers")
        return self.sync()

    def list(self, query: str = "", tags=()) -> list[sqlite3.Row]:
        """Recordings matching the words of `query` (titles, notes, transcripts) and every tag;
        `#word` in the query is a tag too, and `#category:` any tag of that category."""
        words, tags = parse_query(query, tags)
        sql = "SELECT r.* FROM recordings r"
        args: list = []
        where = []
        groups = [self.match_names(p) for p in parse_people(query)]
        if any(not g for g in groups):
            return []  # nobody by that name speaks anywhere
        for names in groups:
            where.append(f"r.id IN (SELECT id FROM speakers WHERE name_folded IN ({_marks(names)}))")
            args += sorted(names)
        if words and groups:
            # The words must be in what those people said, not anywhere in the transcript.
            people = set().union(*groups)
            where.append(f"r.id IN (SELECT id FROM spoken WHERE spoken MATCH ? AND person IN ({_marks(people)}))")
            args += [_match(words), *sorted(people)]
        elif words:
            sql += " JOIN search s ON s.id = r.id"
            where.append("search MATCH ?")
            args.append(_match(words))
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

    def match_names(self, token: str) -> set[str]:
        """Folded names of speakers that `@token` means: the token's words (split at "_"), each
        the start of consecutive words of the name ("ana" and "ana_lo" mean "Ana López")."""
        want = [w for w in fold_tag(token).split("_") if w]
        out = set()
        for (name,) in self.db.execute("SELECT DISTINCT name_folded FROM speakers"):
            have = re.split(r"[\s\-]+", name)
            for i in range(len(have) - len(want) + 1):
                if want and all(have[i + j].startswith(w) for j, w in enumerate(want)):
                    out.add(name)
                    break
        return out

    def speakers(self) -> list[tuple[str, int]]:
        """(name as most often given, recordings) for every named speaker, most recordings first."""
        rows = self.db.execute("SELECT name_folded, name, COUNT(DISTINCT id) n FROM speakers "
                               "GROUP BY name_folded, name").fetchall()
        best: dict[str, tuple[str, int, int]] = {}
        for r in rows:
            spelling, n, total = best.get(r["name_folded"], (r["name"], 0, 0))
            if r["n"] > n:
                spelling, n = r["name"], r["n"]
            best[r["name_folded"]] = (spelling, n, total + r["n"])
        return sorted(((s, t) for s, _n, t in best.values()), key=lambda x: (-x[1], fold_tag(x[0])))

    def speech_matches(self, query: str) -> dict[str, dict]:
        """For a search with `@name` and words: per recording, the speaker numbers searched for and
        a snippet of what they said around the words ({"numbers", "snippet"})."""
        words, _tags = parse_query(query)
        groups = [self.match_names(p) for p in parse_people(query)]
        if not groups or any(not g for g in groups):
            return {}
        people = set().union(*groups)
        out: dict[str, dict] = {}
        for r in self.db.execute(f"SELECT id, number FROM speakers WHERE name_folded IN ({_marks(people)})",
                                 sorted(people)):
            out.setdefault(r["id"], {"numbers": [], "snippet": None})["numbers"].append(r["number"])
        if words:
            rows = self.db.execute(
                "SELECT s.id, k.name, snippet(spoken, 2, '', '', '…', 12) snip FROM spoken s "
                f"JOIN speakers k ON k.id = s.id AND k.name_folded = s.person "
                f"WHERE spoken MATCH ? AND s.person IN ({_marks(people)})", [_match(words), *sorted(people)])
            for r in rows:
                if r["id"] in out and out[r["id"]]["snippet"] is None:
                    out[r["id"]]["snippet"] = f"{r['name']}: {r['snip']}"
        return out

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
    """Split a search into words and tags ("#entrevista"); people ("@ana") are in neither."""
    words, out_tags = [], list(tags)
    for tok in query.split():
        if tok.startswith("#") and len(tok) > 1:
            out_tags.append(tok[1:])
        elif tok != "#" and not tok.startswith("@"):
            words.append(tok)
    return words, out_tags


def parse_people(query: str) -> list[str]:
    """The people of a search: "@ana" and "@ana_lopez" give "ana" and "ana_lopez"."""
    return [tok[1:] for tok in query.split() if tok.startswith("@") and len(tok) > 1]


def _marks(items) -> str:
    return ",".join("?" * len(items))


def _match(words: list[str]) -> str:
    """Words as an FTS5 query: each a prefix, all required."""
    return " ".join(f'"{w.replace(chr(34), "")}"*' for w in words)


def _named_speech(rec: Recording) -> dict[int, tuple[str, str, float]]:
    """Per named speaker: (name, what they said in the shown text, seconds of their passages)."""
    from . import export

    names = rec.meta.speakers
    if rec.meta.speakers_off or not names or not (rec.transcript() or {}).get("speakers"):
        return {}
    out: dict[int, list] = {}
    try:
        cues = export.cues(rec)
    except (OSError, ValueError):
        return {}
    for start, end, text, _para, who in cues:
        name = names.get(str(who)) if who is not None else None
        if name:
            entry = out.setdefault(int(who), [name, [], 0.0])
            entry[1].append(text)
            entry[2] += end - start
    return {n: (name, "\n".join(parts), secs) for n, (name, parts, secs) in out.items()}
