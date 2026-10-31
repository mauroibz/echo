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

from . import config, llm, templates

FILE = "summary.json"
VERSION = 1
SINGLE_MAX = 60_000  # characters in one request: the comparison's longest input was 41,000
PART_MAX = 40_000  # each part of a longer transcript

PROMPT = """You are a meeting note-taker. Given a transcript, write a structured summary of it.

Rules:
{structure}
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

GUIDE = """

The person who recorded this wrote notes and marked moments while it happened; they are what
mattered to them. Build the summary around them: cover each one, expanded from what was said
about it (for a marked moment, around the passage given with it), and fill in the rest of the
transcript around them. Do not quote the notes as notes or mention that they exist."""

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


MARK_BEFORE_S, MARK_AFTER_S = 30.0, 15.0  # the passage sent with a marker: what led to it, and a little after
MARK_PASSAGE_MAX = 600  # characters of it


def guide(rec: Recording) -> str:
    """The user's notes and markers, as sent ahead of the transcript; "" when there are none."""
    lines = []
    notes = (rec.meta.notes or "").strip()
    if notes:
        lines += ["Notes:", notes]
    segs = (rec.transcript() or {}).get("segments") or []
    marks = []
    for m in rec.meta.markers or []:
        at = float(m.get("at", 0))
        near = " ".join((sg.get("text") or "").strip() for sg in segs
                        if at - MARK_BEFORE_S <= float(sg.get("start", 0)) <= at + MARK_AFTER_S).strip()
        if len(near) > MARK_PASSAGE_MAX:
            near = "…" + near[-MARK_PASSAGE_MAX:]
        note = (m.get("note") or "").strip() or "(no note)"
        marks.append(f"- at {export.stamp(at)}: {note}" + (f"\n  Said around it: {near}" if near else ""))
    if marks:
        lines += ([""] if lines else []) + ["Marked moments:"] + marks
    return "\n".join(lines)


def source_sha(rec: Recording) -> str:
    """The hash of what a summary is made from: the transcript and, when there are any, the notes and
    markers, the template and the calendar event, so editing a note or changing the template marks
    the summary out of date. Without them, the transcript's alone, as summaries made before those existed."""
    text, g = source_text(rec), guide(rec)
    name, guidance = templates.resolve(rec)
    ev = "\n".join(event_lines(rec))
    lead = "\n".join(x for x in (f"template {name} {templates.sha(guidance)}" if name else "", g,
                                 f"event {sha(ev)}" if ev else "") if x)
    return sha(f"{lead}\n\n{text}" if lead else text)


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
    lines += event_lines(rec)
    return "\n".join(lines)


EVENT_DESCRIPTION_MAX = 1500  # characters of the invitation's text: its agenda, not its boilerplate


def event_lines(rec: Recording) -> list[str]:
    """The calendar event the recording was made in, as context: its title, who was invited and
    the start of its description (without the video call's links and dial-in numbers)."""
    from . import calendar

    ev = calendar.event_of(rec)
    if ev is None:
        return []
    out = [f"Calendar event: {ev.title}"]
    invited = [f"{a.name} <{a.email}>" if a.name else a.email for a in ev.attendees if a.status != "DECLINED"]
    if invited:
        out.append(f"Invited: {', '.join(invited)}")
    desc = "\n".join(ln for ln in ev.description.splitlines()
                     if ln.strip() and "http" not in ln and not re.search(r"\d{3}[\s-]?\d{3}[\s-]?\d{3,}", ln))
    if desc.strip():
        out.append("Invitation: " + " ".join(desc.split())[:EVENT_DESCRIPTION_MAX])
    return out


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
    template, structure = templates.resolve(rec)
    system = PROMPT.format(structure=structure, next_steps=next_steps(lang),
                           language=LANGUAGES.get(lang, lang))
    head = _header(rec)
    made_from = source_sha(rec)  # before the requests: an edit made meanwhile leaves the summary stale
    g = guide(rec)
    if g:
        system += GUIDE
        head += f"\n\n{g}"
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
        merge = MERGE.format(rules=rules, next_steps=next_steps(lang)) + (GUIDE if g else "")
        out = llm.complete(merge, f"{head}\n\n{merged}", cfg)
    out = _clean(out)
    if not out:
        raise llm.LLMError("the server returned an empty summary")
    data = {"version": VERSION, "text": out, "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "model": cfg.llm_model, "server": config.host(cfg.llm_url), "language": lang,
            "template": template, "source_sha256": made_from}
    atomic_write_json(rec.path(FILE), data)
    return data


TITLE_PROMPT = """Write a title for this meeting from its summary: at most 8 words, in {language},
naming what it was about (and with whom, when that is clear). No quotes, no date, no final period.
Output only the title."""
TITLE_MAX = 80


def retitle(rec: Recording, data: dict, cfg: config.Config | None = None) -> str | None:
    """Give the recording a short title from its summary when its title is still automatic (the
    transcript's first sentence); a title the user typed is never touched. Returns the new title."""
    if not rec.meta.title_auto:
        return None
    lang = data.get("language") or language(rec)
    title = llm.complete(TITLE_PROMPT.format(language=LANGUAGES.get(lang, lang)), data["text"], cfg)
    title = " ".join(title.strip().strip('"“”«»').split()).rstrip(".")[:TITLE_MAX].strip()
    rec.reload()
    if not title or not rec.meta.title_auto:  # renamed by the user meanwhile
        return None
    rec.update(title=title)  # still automatic: a new transcript may replace it, and then a new summary
    return title


def load(rec: Recording) -> dict | None:
    try:
        d = read_json(rec.path(FILE))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("text"), str) else None


def stale(rec: Recording, data: dict | None = None) -> bool:
    """The transcript, notes or markers changed since the summary was made."""
    data = data if data is not None else load(rec)
    return data is not None and data.get("source_sha256") != source_sha(rec)


def demoted(text: str, levels: int = 2) -> str:
    """The summary's headings under a note's own: # becomes ###."""
    return re.sub(r"^(#{1,4}) ", lambda m: "#" * (len(m.group(1)) + levels) + " ", text, flags=re.MULTILINE)


def finish(rec: Recording, data: dict, cfg: config.Config | None = None) -> list[str]:
    """What follows a new summary: the title (when automatic and wanted), each person's part and the
    action items. A
    failure here leaves the summary saved; the returned lines say what did not work."""
    from . import actions

    cfg = cfg or config.load()
    notes = []
    if cfg.auto_title:
        try:
            if title := retitle(rec, data, cfg):
                notes.append(f"titled “{title}”")
        except llm.LLMError as e:
            notes.append(f"no title: {e}")
    from . import parts

    try:
        if (p := parts.write(rec, data, cfg)) is not None:
            notes.append(f"parts for {len(p['parts'])} of {len(parts.names(rec))} people")
    except llm.LLMError as e:
        notes.append(f"no parts: {e}")
    try:
        n = len(actions.write(rec, data, cfg)["items"])
        notes.append(f"{n} action item{'s' if n != 1 else ''}")
    except llm.LLMError as e:
        notes.append(f"no action items: {e}")
    return notes

