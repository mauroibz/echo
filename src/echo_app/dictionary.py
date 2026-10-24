"""Known people and terms (stdlib only): the store, the context sentence, learning, correction.

The dictionary is ``glossary.toml`` in the config folder, plain enough to edit by hand::

    muted = ["Cosa"]

    [[people]]
    name = "Lucía Fernández"
    aliases = ["Lucia Fernandez"]
    used = "2026-10-24T10:00:00+02:00"

    [[terms]]
    name = "Surus"
    aliases = ["surus", "Zurus"]
    used = ""

It is used in two layers. Before transcribing, the most recently used entries become a sentence
in the model's context slot, which makes the model spell them as written. After transcribing,
the corrector replaces the recorded aliases in a copy of the model output
(``transcript.corrected.json``); every replacement is logged so the editor can underline it and
undo it. The model output itself is never changed.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from . import paths
from .fsutil import atomic_write_json, atomic_write_text, read_json
from .library import CORRECTED, EDITED, TRANSCRIPT
from .worker.planning import join_text

log = logging.getLogger(__name__)

PEOPLE = "people"
TERMS = "terms"
KINDS = (PEOPLE, TERMS)
CONTEXT_BUDGET = 120  # tokens of context sentence; the decoder prompt is short
FUZZY_RATIO = 0.9  # multi-token names matched this closely are corrected
CHARS_PER_TOKEN = 3  # conservative for names: the tokenizer splits rare words finely

_WORD = re.compile(r"\w+(?:['’-]\w+)*")


def fold(text: str) -> str:
    """Lower case without accents (ñ stays distinct from n only by case folding rules of NFD)."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).casefold()


def tokens(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _WORD.finditer(text)]


@cache
def common_words() -> frozenset[str]:
    """Folded forms of the 5,000 most frequent Spanish words (see data/es_common.LICENSE.txt)."""
    path = Path(__file__).with_name("data") / "es_common.txt"
    try:
        return frozenset(fold(w) for w in path.read_text(encoding="utf-8").split())
    except OSError:
        return frozenset()


# ---- the store ----------------------------------------------------------------------------------

@dataclass
class Entry:
    kind: str
    name: str
    aliases: list[str] = field(default_factory=list)
    used: str = ""  # ISO time of the last transcription request that included it

    def spellings(self) -> list[str]:
        return [self.name, *self.aliases]


@dataclass
class Dictionary:
    entries: list[Entry] = field(default_factory=list)
    muted: list[str] = field(default_factory=list)
    path: Path | None = None

    # ---- lookup ----
    def find(self, name: str) -> Entry | None:
        f = fold(name)
        return next((e for e in self.entries if fold(e.name) == f), None)

    def knows(self, word: str) -> bool:
        """True if the word is an entry, one of its aliases or muted."""
        f = fold(word)
        if any(fold(m) == f for m in self.muted):
            return True
        return any(fold(s) == f for e in self.entries for s in e.spellings())

    def is_muted(self, word: str) -> bool:
        f = fold(word)
        return any(fold(m) == f for m in self.muted)

    # ---- changes ----
    def add(self, kind: str, name: str, aliases=()) -> Entry:
        """Add an entry, or merge the aliases into the existing one with that name."""
        if kind not in KINDS:
            raise ValueError(kind)
        name = " ".join(name.split())
        if not name:
            raise ValueError("empty name")
        e = self.find(name)
        if e is None:
            e = Entry(kind, name)
            self.entries.append(e)
        for a in aliases:
            a = " ".join(a.split())
            if a and a != e.name and a not in e.aliases:
                e.aliases.append(a)
        return e

    def remove(self, name: str) -> bool:
        e = self.find(name)
        if e is None:
            return False
        self.entries.remove(e)
        _rename_voice(e.name, None)
        return True

    def merge(self, source: str, target: str) -> Entry:
        """Fold `source` into `target`: one entry remains with the aliases of both."""
        src, dst = self.find(source), self.find(target)
        if src is None or dst is None or src is dst:
            raise KeyError(source if src is None else target)
        for s in src.spellings():
            if s != dst.name and s not in dst.aliases:
                dst.aliases.append(s)
        dst.used = max(dst.used, src.used)
        self.entries.remove(src)
        _rename_voice(src.name, dst.name)
        return dst

    def mute(self, word: str) -> None:
        if not self.is_muted(word):
            self.muted.append(word)

    def touch(self, names, when: str | None = None) -> None:
        when = when or datetime.now().astimezone().isoformat(timespec="seconds")
        for n in names:
            e = self.find(n)
            if e is not None:
                e.used = when

    # ---- persistence ----
    def save(self, path: Path | None = None) -> None:
        path = path or self.path or dictionary_path()
        lines = ["# Echo dictionary: people and terms, learned from your corrections. Hand edits are fine.\n"]
        lines.append(f"muted = {_toml_list(self.muted)}\n")
        for kind in KINDS:
            for e in sorted((e for e in self.entries if e.kind == kind), key=lambda e: fold(e.name)):
                lines.append(f"\n[[{kind}]]\nname = {_toml_str(e.name)}\naliases = {_toml_list(e.aliases)}\n"
                             f"used = {_toml_str(e.used)}\n")
        atomic_write_text(path, "".join(lines), mkdir=True)
        self.path = path

    def version(self) -> str:
        """Changes whenever anything the corrector uses changes."""
        data = sorted((e.kind, e.name, tuple(e.aliases)) for e in self.entries)
        return hashlib.sha256(json.dumps([data, sorted(self.muted)], ensure_ascii=False).encode()).hexdigest()[:16]


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_list(items) -> str:
    return "[" + ", ".join(_toml_str(i) for i in items) + "]"


def dictionary_path() -> Path:
    return paths.config_dir() / "glossary.toml"


def load(path: Path | None = None) -> Dictionary:
    """Read the dictionary; a missing file is empty, an unreadable one is kept aside."""
    path = path or dictionary_path()
    d = Dictionary(path=path)
    if not path.exists():
        return d
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as e:
        log.warning("dictionary unreadable (%s); starting empty, old file kept as .bad", e)
        try:
            path.replace(path.with_suffix(".toml.bad"))
        except OSError:
            pass
        return d
    d.muted = [m for m in raw.get("muted", []) if isinstance(m, str)]
    for kind in KINDS:
        for item in raw.get(kind, []):
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
                continue
            aliases = [a for a in item.get("aliases", []) if isinstance(a, str)]
            used = item.get("used", "")
            d.entries.append(Entry(kind, item["name"].strip(), aliases, used if isinstance(used, str) else str(used)))
    return d


_cached: tuple[tuple[int, int] | None, Dictionary] | None = None


def current() -> Dictionary:
    """The dictionary, re-read only when the file changed (the window asks every second)."""
    global _cached
    path = dictionary_path()
    try:
        st = path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    if _cached is None or _cached[0] != stamp or _cached[1].path != path:
        _cached = (stamp, load(path))
    return _cached[1]


def update(change) -> Dictionary:
    """Load, apply `change(d)`, save, and return the saved dictionary."""
    d = load()
    change(d)
    d.save()
    return current()


# ---- voices ----------------------------------------------------------------------------------
# A person named as a speaker keeps a voice signature (the average of their speaker centroids),
# so later recordings can suggest them. Kept next to the dictionary rather than in it: 256
# numbers per person would bury the names in a file meant for reading.

def voices_path() -> Path:
    return paths.config_dir() / "voices.json"


def voices() -> dict[str, dict]:
    try:
        data = read_json(voices_path())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember_voice(name: str, centroid: list[float]) -> None:
    """Fold a speaker's centroid into the person's voice (a running mean over recordings)."""
    data = voices()
    old = data.get(name)
    if old and len(old.get("voice", [])) == len(centroid):
        n = int(old.get("recordings", 1))
        voice = [(a * n + b) / (n + 1) for a, b in zip(old["voice"], centroid)]
        data[name] = {"voice": [round(x, 5) for x in voice], "recordings": n + 1}
    else:
        data[name] = {"voice": [round(float(x), 5) for x in centroid], "recordings": 1}
    atomic_write_json(voices_path(), data, mkdir=True)


def recognize(centroid, similarity, threshold: float) -> str | None:
    """The person whose voice is closest to `centroid`, if at least `threshold` similar."""
    best, score = None, threshold
    for name, v in voices().items():
        if len(v.get("voice", [])) == len(centroid):
            s = similarity(centroid, v["voice"])
            if s >= score:
                best, score = name, s
    return best


def _rename_voice(old: str, new: str | None) -> None:
    data = voices()
    if old in data:
        v = data.pop(old)
        if new and new not in data:
            data[new] = v
        atomic_write_json(voices_path(), data, mkdir=True)


# ---- the context sentence --------------------------------------------------------------------

def context_sentence(d: Dictionary, extra_line: str = "", budget: int = CONTEXT_BUDGET) -> tuple[str, list[str]]:
    """The text for the model's context slot, and the entry names it includes.

    The recording's own line goes first, verbatim; then "Personas: A, B. Términos: C, D." with
    people before terms and each group most recently used first, cut at the budget by whole
    entries.
    """
    line = " ".join(extra_line.split())
    if line and line[-1] not in ".!?…":
        line += "."
    remaining = budget - len(line) // CHARS_PER_TOKEN
    groups = []
    included = []
    for kind, label in ((PEOPLE, "Personas"), (TERMS, "Términos")):
        names = []
        cost = len(label) // CHARS_PER_TOKEN + 2
        for e in sorted((e for e in d.entries if e.kind == kind), key=lambda e: e.used, reverse=True):
            c = len(e.name) // CHARS_PER_TOKEN + 2
            if remaining - cost - c < 0:
                break
            names.append(e.name)
            cost += c
        if names:
            remaining -= cost
            groups.append(f"{label}: {', '.join(names)}.")
            included += names
    return " ".join(p for p in [line, *groups] if p), included


# ---- learning from corrections ----------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    kind: str
    name: str
    alias: str = ""  # the model's spelling, recorded as an alias when accepted


def _seen_path() -> Path:
    return paths.state_dir() / "candidates.json"


def _load_seen() -> dict[str, list[str]]:
    try:
        data = read_json(_seen_path())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def kind_of(name: str) -> str:
    """Two or more capitalized words look like a person's name; anything else is a term."""
    caps = [t for _a, _b, t in tokens(name) if t[:1].isupper()]
    return PEOPLE if len(caps) >= 2 else TERMS


def _sentence_start(text: str, pos: int) -> bool:
    i = pos - 1
    while i >= 0 and text[i] in " \t\"'«“(":
        i -= 1
    return i < 0 or text[i] in ".!?¿¡…\n:"


def replacements(model_text: str, edited_text: str) -> list[tuple[str, str, int]]:
    """(model words, edited words, position in the edited text) for every replacement of one to
    three words, found by aligning the folded words of both texts."""
    mt, et = tokens(model_text), tokens(edited_text)
    sm = difflib.SequenceMatcher(None, [fold(t) for *_x, t in mt], [fold(t) for *_x, t in et], autojunk=False)
    changes: list[list[int]] = []  # [model start, model end, edited start, edited end] in tokens
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        # An "equal" folded run can still hide case or accent changes ("surus" -> "Surus").
        if op == "equal":
            parts = [[i1 + k, i1 + k + 1, j1 + k, j1 + k + 1] for k in range(i2 - i1) if mt[i1 + k][2] != et[j1 + k][2]]
        elif op == "replace":
            parts = [[i1, i2, j1, j2]]
        else:
            parts = []
        for part in parts:
            # Adjacent changes are one replacement: "lucia fernandes" -> "Lucía Fernández".
            if changes and changes[-1][1] == part[0] and changes[-1][3] == part[2] and part[2] > 0 \
                    and not edited_text[et[part[2] - 1][1]:et[part[2]][0]].strip():
                changes[-1][1], changes[-1][3] = part[1], part[3]
            else:
                changes.append(part)
    out = []
    for a1, a2, b1, b2 in changes:
        if 1 <= b2 - b1 <= 3:
            before = model_text[mt[a1][0]:mt[a2 - 1][1]]
            after = edited_text[et[b1][0]:et[b2 - 1][1]]
            if before != after:
                out.append((before, after, et[b1][0]))
    return out


def edit_candidates(model_text: str, edited_text: str, d: Dictionary, rec_id: str = "",
                    remember: bool = True) -> list[Candidate]:
    """Words the user replaced that look like names or terms worth learning.

    A replacement of one to three words qualifies when its new spelling starts with a capital
    letter away from a sentence start, or when the same replacement was made in another
    recording. Known and muted words are skipped, and so are pure case or accent changes of
    common words ("como" → "cómo"). With `remember`, replacements are counted per recording in
    the state folder so a second recording can confirm a lower-case term.
    """
    seen = _load_seen()
    changed_seen = False
    out: list[Candidate] = []
    common = common_words()
    for before, after, pos in replacements(model_text, edited_text):
        if d.knows(after):
            continue
        words = [fold(t) for *_x, t in tokens(after)]
        if fold(before) == fold(after) and all(w in common for w in words):
            continue  # case or accent fix of ordinary words
        key = f"{fold(before)}\t{after}"
        recs = seen.setdefault(key, [])
        if rec_id and rec_id not in recs:
            recs.append(rec_id)
            changed_seen = True
        capital = after[:1].isupper() and not _sentence_start(edited_text, pos)
        twice = len(recs) >= 2
        if not (capital or twice):
            continue
        if len(words) == 1 and words[0] in common and not capital:
            continue
        cand = Candidate(kind_of(after), after, before)
        if cand not in out:
            out.append(cand)
    if remember and changed_seen:
        try:
            atomic_write_json(_seen_path(), seen, mkdir=True)
        except OSError:
            pass
    return out


def new_aliases(model_text: str, edited_text: str, d: Dictionary) -> list[tuple[str, str]]:
    """(entry name, model spelling) where the user corrected a known name from a spelling the
    dictionary did not have yet: that spelling becomes another alias, so it is fixed everywhere."""
    out = []
    common = common_words()
    for before, after, _pos in replacements(model_text, edited_text):
        e = d.find(after)
        words = [fold(t) for *_x, t in tokens(before)]
        if e is None or d.knows(before) or (len(words) == 1 and words[0] in common):
            continue
        if (e.name, before) not in out:
            out.append((e.name, before))
    return out


def title_candidates(title: str, first_sentence: str, d: Dictionary) -> list[Candidate]:
    """Capitalized words in a title the user typed, other than its first word and common words."""
    out = []
    first_folded = {fold(t) for *_x, t in tokens(first_sentence)}
    toks = tokens(title)
    common = common_words()
    run: list[tuple[int, int, str]] = []

    def flush():
        # Titles start with a capital anyway: a common first word is not part of a name
        # ("Charla Surus"), and any first word counts only as part of a longer one.
        if run and run[0] is toks[0] and (len(run) == 1 or fold(run[0][2]) in common):
            run.pop(0)
        if run:
            name = title[run[0][0]:run[-1][1]]
            if not d.knows(name) and not (len(run) == 1 and fold(name) in common) \
                    and not all(fold(t) in first_folded for *_x, t in run):
                out.append(Candidate(kind_of(name), name))
        run.clear()

    for tok in toks:
        word = tok[2]
        if word[:1].isupper() and not word.isdigit():
            if run and title[run[-1][1]:tok[0]].strip():
                flush()
            run.append(tok)
        else:
            flush()
    flush()
    return out[:3]


# ---- the corrector ---------------------------------------------------------------------------

def _replacements(d: Dictionary) -> list[tuple[list[str], str]]:
    """(folded tokens, canonical name) for every spelling to replace, longest first.

    The canonical name is included so the model's case variants ("surus") are fixed too. A
    single common word is never a spelling to replace: "luz" stays "luz" even with a Luz in the
    dictionary.
    """
    out = []
    common = common_words()
    for e in d.entries:
        for spelling in e.spellings():
            words = [fold(t) for *_x, t in tokens(spelling)]
            if words and not (len(words) == 1 and words[0] in common):
                out.append((words, e.name))
    out.sort(key=lambda r: -len(r[0]))
    return out


def correct_segment(text: str, d: Dictionary, rejected: set[tuple[int, str]] = frozenset()) \
        -> tuple[str, list[dict[str, Any]]]:
    """Apply the dictionary to one passage. Returns (text, edits); positions refer to `text` as
    returned, `pos` to the original. Rejected (pos, before) pairs are left alone."""
    toks = tokens(text)
    folded = [fold(t) for *_x, t in toks]
    reps = _replacements(d)
    multi = [(e.name, [fold(t) for *_x, t in tokens(e.name)]) for e in d.entries
             if len(tokens(e.name)) >= 2]
    found: list[tuple[int, int, str]] = []  # token start, token end (exclusive), replacement
    taken = [False] * len(toks)
    for words, name in reps:
        n = len(words)
        for i in range(len(toks) - n + 1):
            if folded[i:i + n] == words and not any(taken[i:i + n]):
                found.append((i, i + n, name))
                for k in range(i, i + n):
                    taken[k] = True
    for name, words in multi:
        n = len(words)
        target = " ".join(words)
        for i in range(len(toks) - n + 1):
            if any(taken[i:i + n]):
                continue
            window = " ".join(folded[i:i + n])
            if window != target and difflib.SequenceMatcher(None, window, target).ratio() >= FUZZY_RATIO:
                found.append((i, i + n, name))
                for k in range(i, i + n):
                    taken[k] = True
    found.sort()
    out, edits, last, shift = [], [], 0, 0
    for i, j, name in found:
        a, b = toks[i][0], toks[j - 1][1]
        before = text[a:b]
        if before == name or (a, before) in rejected:
            continue
        out.append(text[last:a])
        start = a + shift
        out.append(name)
        edits.append({"pos": a, "start": start, "end": start + len(name), "before": before, "after": name})
        shift += len(name) - len(before)
        last = b
    out.append(text[last:])
    return "".join(out), edits


def correct(segments: list[dict], d: Dictionary, rejected: list[dict] = ()) -> tuple[list[str], list[dict]]:
    """Corrected text of every segment and the edits, each tagged with its segment index."""
    rej: dict[int, set[tuple[int, str]]] = {}
    for r in rejected:
        rej.setdefault(r.get("segment", -1), set()).add((r.get("pos", -1), r.get("before", "")))
    texts, edits = [], []
    for k, seg in enumerate(segments):
        text, es = correct_segment(seg.get("text") or "", d, rej.get(k, set()))
        texts.append(text)
        for e in es:
            edits.append({"segment": k, **e})
    return texts, edits


def apply(rec, d: Dictionary | None = None) -> bool:
    """Bring a recording's corrected copy up to date with the dictionary. Returns True if the
    file changed. Nothing is written for a recording the user has edited (their text wins) or
    whose transcript needs no correction."""
    t = rec.transcript()
    path = rec.path(CORRECTED)
    if t is None or not rec.path(TRANSCRIPT).exists():
        return False
    d = d if d is not None else load()
    old = read_corrected(rec)
    created = t.get("created", "")
    rejected = old.get("rejected", []) if old and old.get("transcript_created") == created else []
    if old and old.get("transcript_created") == created and old.get("dictionary") == d.version():
        return False
    if rec.path(EDITED).exists():
        return False  # the user's text is what they see; it is never corrected
    texts, edits = correct(t.get("segments", []), d, rejected)
    if not edits and not rejected:
        if path.exists():
            path.unlink()
            return True
        return False
    segs = [{**s, "text": tx} for s, tx in zip(t.get("segments", []), texts)]
    atomic_write_json(path, {"version": 1, "transcript_created": created, "dictionary": d.version(),
                             "segments": texts, "text": join_text(segs, t.get("language", "es")), "edits": edits, "rejected": rejected})
    return True


def read_corrected(rec) -> dict | None:
    try:
        data = read_json(rec.path(CORRECTED))
    except (FileNotFoundError, ValueError):
        return None
    t = rec.transcript() or {}
    if data.get("transcript_created") != t.get("created"):
        return None  # left over from an earlier model run
    return data


def undo(rec, edit: dict) -> None:
    """Restore the model's spelling at one corrected spot and remember not to correct it again."""
    data = read_corrected(rec)
    if data is None:
        return
    data.setdefault("rejected", []).append({"segment": edit["segment"], "pos": edit["pos"], "before": edit["before"]})
    data["dictionary"] = ""  # force a recompute with the new rejection
    atomic_write_json(rec.path(CORRECTED), data)
    apply(rec)
