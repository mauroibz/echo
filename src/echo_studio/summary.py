"""A recording's summary: the prompt, long transcripts in parts, and summary.json (stdlib only).

One request per summary. An earlier comparison on ten Spanish meetings of 17,000 to 41,000
characters found one request with an explicit structure and length target better than
extracting metadata first, a self-critique pass or classifying the meeting first (0.61 against
0.56-0.58 from a second model scoring against reference summaries); those also made summaries
20-50% longer. Every approach invented a summary for a recording that was mostly unrelated audio,
hence the rule about it below.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from echo_app import export
from echo_app.fsutil import atomic_write_json, read_json
from echo_app.library import Recording

from . import config, llm

FILE = "summary.json"
VERSION = 1
SINGLE_MAX = 60_000  # characters in one request: the comparison's longest input was 41,000
PART_MAX = 40_000  # each part of a longer transcript

PROMPT = """You are a meeting note-taker. Given a transcript, write a structured summary of it.

Rules:
- Group the content by topic, not in the order it was said, in 4 to 7 sections, each with a
  single # heading. Use no ## or ### headings.
- Everything under a heading is bullet points (- ), at most two levels deep.
- The last section is "{next_steps}": each action as **the action in bold** (who does it),
  with a line of context under it. Leave the section out if nothing was agreed.
- Keep names, numbers, dates and decisions exactly as said. Use ~ for approximate numbers.
- When someone is introduced, write "Name: who they are".
- Write in {language}.
- Aim for 5 to 10% of the transcript's length. Shorter is better than padded.
- Lines start with "Name:" where the speaker changes; say who said or decided something when it
  matters, but never mention speaker labels such as "Speaker 2".
- If most of the transcript is unrelated to the conversation (another person's audio, a video
  playing, background talk), say so in one line at the top and summarize only the rest; if
  nothing is left, say only that.
- Output only the summary, with no preamble and no closing remarks."""

PART_NOTE = ("\n\nThis is part {n} of {m} of one long transcript. Summarize only this part; "
             "the parts are merged afterwards.")

MERGE = """You are a meeting note-taker. These are summaries of consecutive parts of one long
meeting, in order. Merge them into one summary of the whole meeting, following the same rules:

{rules}

Join topics that appear in several parts, keep every decision and action, and write one
"{next_steps}" section at the end."""

LANGUAGES = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French", "it": "Italian",
             "de": "German"}


def language(rec: Recording) -> str:
    return (rec.transcript() or {}).get("language") or rec.meta.language or "es"


def next_steps(lang: str) -> str:
    return "Próximos pasos" if lang == "es" else "Next steps"


def heading(rec: Recording) -> str:
    return "Resumen" if language(rec) == "es" else "Summary"


def source_text(rec: Recording) -> str:
    """What is sent: the text the user sees, with "Name:" where the speaker changes."""
    if rec.transcript() and export.has_speakers(rec):
        return export.with_speakers(rec).strip()
    return rec.text().strip()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split(text: str, limit: int = PART_MAX) -> list[str]:
    """Parts of at most `limit` characters, cut between paragraphs (inside one only if it is longer)."""
    parts: list[str] = []
    cur = ""
    for para in text.split("\n\n"):
        while len(para) > limit:  # one paragraph longer than a part: cut at the last sentence end
            cut = max(para.rfind(". ", 0, limit), para.rfind("? ", 0, limit), para.rfind("! ", 0, limit))
            cut = cut + 1 if cut > limit // 2 else limit
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(para[:cut].strip())
            para = para[cut:].strip()
        if cur and len(cur) + 2 + len(para) > limit:
            parts.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        parts.append(cur)
    return parts


def _header(rec: Recording) -> str:
    try:
        when = datetime.fromisoformat(rec.meta.created).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        when = rec.meta.created
    lines = [f"Title: {rec.meta.title}", f"Date: {when}"]
    if rec.meta.context_line:
        lines.append(f"About: {rec.meta.context_line}")
    names = [n for n in dict.fromkeys(rec.meta.speakers.values()) if n]
    if names:
        lines.append(f"People: {', '.join(names)}")
    return "\n".join(lines)


def _clean(text: str) -> str:
    text = text.strip()
    if text.endswith("---"):  # a separator some models add at the end
        text = text[:-3].rstrip()
    return text


def write(rec: Recording, progress=None, cfg: config.Config | None = None) -> dict:
    """Summarize the recording and save summary.json; returns what was saved.

    `progress(done, total)` is called before each request. Raises llm.LLMError, or ValueError when
    there is no text, leaving an earlier summary as it was.
    """
    cfg = cfg or config.load()
    text = source_text(rec)
    if not text:
        raise ValueError("this recording has no transcript to summarize")
    lang = language(rec)
    system = PROMPT.format(next_steps=next_steps(lang), language=LANGUAGES.get(lang, lang))
    head = _header(rec)
    if len(text) <= SINGLE_MAX:
        if progress:
            progress(0, 1)
        out = llm.complete(system, f"{head}\n\nTranscript:\n\n{text}", cfg)
    else:
        parts = split(text)
        total = len(parts) + 1
        pieces = []
        for n, part in enumerate(parts, 1):
            if progress:
                progress(n - 1, total)
            pieces.append(_clean(llm.complete(system + PART_NOTE.format(n=n, m=len(parts)),
                                              f"{head}\n\nTranscript, part {n} of {len(parts)}:\n\n{part}", cfg)))
        if progress:
            progress(len(parts), total)
        rules = system.split("Rules:\n", 1)[1]
        merged = "\n\n".join(f"Part {n}:\n\n{p}" for n, p in enumerate(pieces, 1))
        out = llm.complete(MERGE.format(rules=rules, next_steps=next_steps(lang)), f"{head}\n\n{merged}", cfg)
    out = _clean(out)
    if not out:
        raise llm.LLMError("the server returned an empty summary")
    data = {"version": VERSION, "text": out, "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "model": cfg.llm_model, "server": config.host(cfg.llm_url), "language": lang, "source_sha256": sha(text)}
    atomic_write_json(rec.path(FILE), data)
    return data


def load(rec: Recording) -> dict | None:
    try:
        d = read_json(rec.path(FILE))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("text"), str) else None


def stale(rec: Recording, data: dict | None = None) -> bool:
    """The transcript changed since the summary was made."""
    data = data if data is not None else load(rec)
    return data is not None and data.get("source_sha256") != sha(source_text(rec))


def demoted(text: str, levels: int = 2) -> str:
    """The summary's headings under a note's own: # becomes ###."""
    return re.sub(r"^(#{1,4}) ", lambda m: "#" * (len(m.group(1)) + levels) + " ", text, flags=re.MULTILINE)
