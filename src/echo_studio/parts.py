"""Each participant's part in a meeting, one line per person, in parts.json (stdlib only).

A person's page lists their meetings with the minutes' excerpt and this line: what they brought,
asked or took on. It comes from one short request over the finished summary and the transcript
with names (when it fits), for everyone named in the recording at once, so a meeting of six costs
one request, not six.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from echo_app import export
from echo_app.fsutil import atomic_write_json, read_json
from echo_app.library import Recording, fold_tag

from . import config, llm, summary

FILE = "parts.json"
VERSION = 1
LINE_MAX = 220

PROMPT = """You describe each person's part in a meeting, from its summary and, when it fits, its
transcript. Answer with a JSON object only, no prose and no code fence: one key per person, exactly
as written here: {names}. Each value is one sentence in {language}, at most 25 words, about what
that person contributed: what they proposed, reported, asked, decided or took on. Concrete, no
praise, no "participated in". Leave out a person who barely spoke."""


def names(rec: Recording) -> list[str]:
    return [n for n in dict.fromkeys(rec.meta.speakers.values()) if n]


def parse(reply: str, wanted: list[str]) -> dict[str, str]:
    """The model's object, tolerant of a fence or text around it, keeping only the asked names
    (compared folded) under their own spelling."""
    m = re.search(r"\{.*\}", reply, re.DOTALL)
    if not m:
        return {}
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return {}
    by_fold = {fold_tag(n): n for n in wanted}
    out = {}
    for k, v in raw.items() if isinstance(raw, dict) else []:
        name = by_fold.get(fold_tag(str(k)))
        line = " ".join(str(v or "").split())
        if name and line:
            out[name] = line[:LINE_MAX]
    return out


def write(rec: Recording, data: dict, cfg: config.Config | None = None) -> dict | None:
    """Ask for everyone's part and save parts.json; None when nobody in the recording is named."""
    who = names(rec)
    if not who:
        return None
    lang = data.get("language") or summary.language(rec)
    user = f"Summary:\n\n{data['text']}"
    text = summary.source_text(rec)
    if text and len(text) <= summary.SINGLE_MAX and rec.transcript():
        user += "\n\nTranscript:\n\n" + export.with_speakers(rec)
    got = parse(llm.complete(PROMPT.format(names=", ".join(who), language=summary.LANGUAGES.get(lang, lang)),
                             user, cfg), who)
    out = {"version": VERSION, "created": datetime.now().astimezone().isoformat(timespec="seconds"),
           "summary_created": data.get("created"), "parts": got}
    atomic_write_json(rec.path(FILE), out)
    return out


def load(rec: Recording) -> dict[str, str]:
    try:
        d = read_json(rec.path(FILE))
    except (OSError, ValueError):
        return {}
    parts = d.get("parts") if isinstance(d, dict) else None
    return {str(k): str(v) for k, v in parts.items()} if isinstance(parts, dict) else {}


def part_of(rec: Recording, name: str) -> str:
    want = fold_tag(name)
    return next((v for k, v in load(rec).items() if fold_tag(k) == want), "")
