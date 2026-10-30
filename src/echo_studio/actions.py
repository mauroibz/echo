"""Action items: a summary's next steps as data, in actions.json (stdlib only).

They come from a second, short request over the finished summary (and the transcript with its
times, when it fits), so the summary prompt stays the one task 1.8 measured and no request is
asked for two formats. Each item has its text, owner (a name as Echo knows it, or ""), due date
(ISO, or ""), the time in the audio where it came up (seconds, or None) and a done flag. Checking
an item rewrites the file; summarizing again keeps the done flags of items whose text is the same.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from echo_app import export
from echo_app.fsutil import atomic_write_json, read_json
from echo_app.library import Recording, fold_tag

from . import config, llm, summary

FILE = "actions.json"
VERSION = 1
WITH_TRANSCRIPT_MAX = summary.SINGLE_MAX  # longer transcripts: the summary alone, items without times

PROMPT = """You extract the action items agreed in a meeting. You get its summary and, when it fits,
its transcript with times. Answer with a JSON array only, no prose and no code fence. One object
per action that someone agreed to do:

{{"text": "the action, short, imperative, in {language}",
  "owner": "who does it, exactly as one of these names if it is one of them: {names}; else as said; else \\"\\"",
  "due": "YYYY-MM-DD if a date or day was said (the meeting was on {date}), else \\"\\"",
  "at": "m:ss or h:mm:ss in the transcript where it was agreed, else \\"\\""}}

Only actions somebody committed to, not topics or ideas. [] when there are none."""


def _stamp_seconds(s: str) -> float | None:
    parts = s.strip().split(":")
    if not 2 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    sec = 0
    for p in parts:
        sec = sec * 60 + int(p)
    return float(sec)


def _names(rec: Recording) -> list[str]:
    return [n for n in dict.fromkeys(rec.meta.speakers.values()) if n]


def parse(reply: str) -> list[dict]:
    """The model's JSON array, tolerant of a code fence or text around it; [] if there is none."""
    m = re.search(r"\[.*\]", reply, re.DOTALL)
    if not m:
        return []
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return []
    items = []
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict) or not str(it.get("text") or "").strip():
            continue
        due = str(it.get("due") or "").strip()
        try:
            datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            due = ""
        items.append({"text": " ".join(str(it["text"]).split()), "owner": str(it.get("owner") or "").strip(),
                      "due": due, "at": _stamp_seconds(str(it.get("at") or "")), "done": False})
    return items


def write(rec: Recording, data: dict, cfg: config.Config | None = None) -> dict:
    """Extract the items from the recording's summary `data` and save actions.json; keeps done flags."""
    lang = data.get("language") or summary.language(rec)
    try:
        date = datetime.fromisoformat(rec.meta.created).strftime("%Y-%m-%d (%A)")
    except ValueError:
        date = rec.meta.created
    system = PROMPT.format(language=summary.LANGUAGES.get(lang, lang), names=", ".join(_names(rec)) or "(none)",
                           date=date)
    user = f"Summary:\n\n{data['text']}"
    text = summary.source_text(rec)
    if text and len(text) <= WITH_TRANSCRIPT_MAX and rec.transcript():
        user += "\n\nTranscript with times:\n\n" + export.with_timestamps(rec)
    items = parse(llm.complete(system, user, cfg))
    old = load(rec)
    done = {fold_tag(i["text"]) for i in (old or {}).get("items", []) if i.get("done")}
    for i in items:
        i["done"] = fold_tag(i["text"]) in done
    out = {"version": VERSION, "created": datetime.now().astimezone().isoformat(timespec="seconds"),
           "summary_created": data.get("created"), "items": items}
    atomic_write_json(rec.path(FILE), out)
    return out


def load(rec: Recording) -> dict | None:
    try:
        d = read_json(rec.path(FILE))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("items"), list) else None


def set_done(rec: Recording, index: int, done: bool) -> None:
    d = load(rec)
    if d is None or not 0 <= index < len(d["items"]):
        return
    d["items"][index]["done"] = bool(done)
    atomic_write_json(rec.path(FILE), d)


def open_items(library, index=None, person: str = "", tags=()) -> list[dict]:
    """Open items across the library, newest recording first, each with its recording's id, title
    and date and its position in the file. `person` keeps one owner's (folded, as tags compare);
    `tags` keeps the recordings with every tag (through the index, as the search does)."""
    if tags and index is not None:
        recs = [r for r in (library.get(row["id"]) for row in index.list("", tags)) if r is not None]
    else:
        recs = sorted(library.all(), key=lambda r: r.meta.created, reverse=True)
    want = fold_tag(person.strip()) if person.strip() else None
    out = []
    for rec in recs:
        d = load(rec)
        for k, it in enumerate((d or {}).get("items", [])):
            if it.get("done") or (want is not None and fold_tag(it.get("owner") or "") != want):
                continue
            out.append({**it, "id": rec.id, "title": rec.meta.title, "created": rec.meta.created, "index": k})
    return out
