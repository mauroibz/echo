"""Action items: a summary's next steps as data, in actions.json (stdlib only).

They come from a second, short request over the finished summary (and the transcript with its
times, when it fits), so the summary prompt stays the one task 1.8 measured and no request is
asked for two formats. Each item has its text (a title), a description (what exactly and why, from
what was said, so the item stands on its own in a tracker), owner (a name as Echo knows it, or
""), due date (ISO, or ""), the time in the audio where it came up (seconds, or None), and what the
user did to it: context for whoever picks it up, a note only for the user, edited, discarded, or
added by hand. Items are informative: whether they
got done is the team tracker's business, so there is no done flag. Summarizing again keeps the
user's work on every item the model gives again (matched by the text the model first gave it)
and keeps the items the user added.
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
VERSION = 2
USER_FIELDS = ("text", "description", "owner", "due", "context", "note", "discarded", "edited")  # what the user may change
DESCRIPTION_MAX = 600
WITH_TRANSCRIPT_MAX = summary.SINGLE_MAX  # longer transcripts: the summary alone, items without times

PROMPT = """You extract the action items agreed in a meeting. You get its summary and, when it fits,
its transcript with times. Answer with a JSON array only, no prose and no code fence. One object
per action that someone agreed to do:

{{"text": "the action as a short title, imperative, in {language}",
  "description": "one to three sentences in {language} that let someone who was not there act on it: what exactly is to be done, why, and the details, names, numbers, constraints or dependencies that were said about it. Only what was said; \"\" if nothing more was said",
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
        new = _item(" ".join(str(it["text"]).split()), str(it.get("owner") or "").strip(), due,
                    _stamp_seconds(str(it.get("at") or "")))
        new["description"] = " ".join(str(it.get("description") or "").split())[:DESCRIPTION_MAX]
        items.append(new)
    return items


def _item(text: str, owner: str = "", due: str = "", at: float | None = None, origin: str = "model") -> dict:
    return {"text": text, "description": "", "owner": owner, "due": due, "at": at, "context": "", "note": "",
            "discarded": False, "edited": False, "origin": origin, "key": fold_tag(text)}


def _upgrade(it: dict) -> dict:
    """An item as version 2 has it; a version 1 item (with a done flag) is a model item."""
    out = _item(str(it.get("text") or ""), str(it.get("owner") or ""), str(it.get("due") or ""), it.get("at"),
                "user" if it.get("origin") == "user" else "model")
    out["key"] = str(it.get("key") or out["key"])
    out["description"] = str(it.get("description") or "")
    out["context"] = str(it.get("context") or "")
    out["note"] = str(it.get("note") or "")
    out["discarded"] = bool(it.get("discarded"))
    out["edited"] = bool(it.get("edited"))
    return out


def merge(new: list[dict], old: list[dict]) -> list[dict]:
    """The new extraction with the user's work carried over: an old model item that was edited,
    given context or a note, or discarded wins over the new item with the same key (its time comes from the
    new one when it had none); old items the user added stay at the end. Old model items the new
    summary no longer has are dropped, as they were only the model's."""
    worked = {i["key"]: i for i in old
              if i.get("origin") == "model" and (i["edited"] or i["context"] or i["note"] or i["discarded"])}
    out = []
    for i in new:
        o = worked.get(i["key"])
        if o is not None:
            i = {**i, **{f: o[f] for f in USER_FIELDS}, "at": o["at"] if o["at"] is not None else i["at"]}
        out.append(i)
    return out + [i for i in old if i.get("origin") == "user"]


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
    items = merge(parse(llm.complete(system, user, cfg)), (load(rec) or {}).get("items", []))
    out = {"version": VERSION, "created": datetime.now().astimezone().isoformat(timespec="seconds"),
           "summary_created": data.get("created"), "items": items}
    atomic_write_json(rec.path(FILE), out)
    return out


def load(rec: Recording) -> dict | None:
    try:
        d = read_json(rec.path(FILE))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("items"), list):
        return None
    d["items"] = [_upgrade(i) for i in d["items"] if isinstance(i, dict) and str(i.get("text") or "").strip()]
    d["version"] = VERSION
    return d


def _save(rec: Recording, d: dict) -> None:
    atomic_write_json(rec.path(FILE), d)


def update(rec: Recording, index: int, **fields) -> None:
    """Change an item's text, description, owner, due date, context or note; the model's fields (text,
    description, owner, date) mark it edited."""
    d = load(rec)
    if d is None or not 0 <= index < len(d["items"]):
        return
    it = d["items"][index]
    for f in ("text", "description", "owner", "due", "context", "note"):
        if f in fields:
            v = str(fields[f] or "").strip() if f in ("context", "note") else " ".join(str(fields[f] or "").split())
            if f not in ("context", "note") and v != it[f]:
                it["edited"] = True
            it[f] = v
    if not it["text"]:
        return  # an item needs words; the editor does not allow saving it empty
    _save(rec, d)


def discard(rec: Recording, index: int, on: bool = True) -> None:
    d = load(rec)
    if d is None or not 0 <= index < len(d["items"]):
        return
    d["items"][index]["discarded"] = bool(on)
    _save(rec, d)


def add(rec: Recording, text: str, owner: str = "", due: str = "", context: str = "", description: str = "",
        note: str = "") -> None:
    """An item the user adds by hand; summarizing again keeps it."""
    text = " ".join(text.split())
    if not text:
        return
    d = load(rec) or {"version": VERSION, "created": datetime.now().astimezone().isoformat(timespec="seconds"),
                      "summary_created": None, "items": []}
    it = _item(text, owner.strip(), due.strip(), origin="user")
    it["context"] = context.strip()
    it["description"] = " ".join(description.split())
    it["note"] = note.strip()
    d["items"].append(it)
    _save(rec, d)


def assigned_to(library, person: str, discarded: bool = False) -> list[dict]:
    """The items assigned to `person` (folded, as tags compare) across the library, newest recording
    first, discarded ones only when asked; each with its recording's id, title and date and its index."""
    want = fold_tag(person.strip())
    out = []
    for rec in sorted(library.all(), key=lambda r: r.meta.created, reverse=True):
        for k, it in enumerate((load(rec) or {}).get("items", [])):
            if (discarded or not it["discarded"]) and want and fold_tag(it["owner"]) == want:
                out.append({**it, "id": rec.id, "title": rec.meta.title, "created": rec.meta.created, "index": k})
    return out
