"""Questions answered from what was said: about one recording, or across the library (stdlib only).

One recording: its transcript with times and speakers goes with the question, and the answer
cites times as [m:ss]. The library: a first short request turns the question into searches
(words, @people, #tags), Echo's index finds the passages, and only those go to the model, which
cites them by number. There are no embeddings and no second index: plain search over the FTS5
index already covers the text and the speakers.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from echo_app import export
from echo_app.library import Recording, fold_tag

from . import config, llm, summary

RECORDING_MAX = 150_000  # characters of timed transcript sent whole; longer ones send the passages that match
LIBRARY_PASSAGES = 60  # passages sent for a question across the library
SEARCHES_MAX = 4

RECORDING_PROMPT = """You answer questions about one meeting from its transcript. Each line starts with
its time, [m:ss]; "Name:" marks who speaks. Answer in {language}, briefly, only from the transcript:
if it does not say, answer that it does not. After each statement, cite the time it comes from as
[m:ss], copied from the line. Name who said what when it matters."""

SEARCH_PROMPT = """You turn a question about past meetings into searches for a full-text index. Answer
with a JSON array only, of at most {n} strings. Each search is a few words that would appear in what
was said (no stop words), optionally with @firstname for a person who spoke and #tag for a
recording's tag. Spelling variants and synonyms go in separate searches. Today is {today}."""

LIBRARY_PROMPT = """You answer questions about past meetings from numbered passages found in their
transcripts; each gives its meeting, date and speaker. Answer in {language}, briefly, only from
the passages: if they do not say, answer that they do not. After each statement cite the passage
numbers it comes from as [n]. Say which meeting and when, when it matters."""

_STAMP = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]")
_REF = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")


def seconds(stamp: str) -> float:
    sec = 0
    for p in stamp.split(":"):
        sec = sec * 60 + int(p)
    return float(sec)


def _history(history: list[tuple[str, str]]) -> str:
    if not history:
        return ""
    return "Earlier in this conversation:\n\n" + "\n\n".join(f"Q: {q}\nA: {a}" for q, a in history) + "\n\n"


def _timed(rec: Recording, question: str) -> str:
    text = export.with_timestamps(rec)
    if len(text) <= RECORDING_MAX:
        return text
    # Too long to send whole: the lines with the question's words, and their neighbours.
    words = [w for w in re.findall(r"\w+", fold_tag(question)) if len(w) > 3]
    lines = text.splitlines()
    keep = set()
    for i, line in enumerate(lines):
        if any(w in fold_tag(line) for w in words):
            keep.update(range(max(0, i - 3), min(len(lines), i + 4)))
    out = "\n".join(lines[i] for i in sorted(keep))
    return out[:RECORDING_MAX] or text[:RECORDING_MAX]


def ask_recording(rec: Recording, question: str, history: list[tuple[str, str]] | None = None,
                  cfg: config.Config | None = None) -> str:
    """The answer, with [m:ss] citations of the recording's times."""
    if not rec.transcript():
        raise ValueError("transcribe this recording first")
    lang = summary.language(rec)
    user = (f"Meeting: {rec.meta.title}\n\nTranscript:\n\n{_timed(rec, question)}\n\n"
            f"{_history(history or [])}Question: {question}")
    return llm.complete(RECORDING_PROMPT.format(language=summary.LANGUAGES.get(lang, lang)), user, cfg)


def searches(question: str, cfg: config.Config | None = None) -> list[str]:
    today = datetime.now().strftime("%Y-%m-%d")
    reply = llm.complete(SEARCH_PROMPT.format(n=SEARCHES_MAX, today=today), question, cfg)
    m = re.search(r"\[.*\]", reply, re.DOTALL)
    try:
        got = json.loads(m.group(0)) if m else []
    except ValueError:
        got = []
    out = [" ".join(str(q).split()) for q in got if isinstance(q, str) and q.strip()][:SEARCHES_MAX]
    return out or [question]


def find_passages(index, queries: list[str], limit: int = LIBRARY_PASSAGES) -> list[dict]:
    """The passages the searches find, without repeats, in the order found."""
    seen, out = set(), []
    for q in queries:
        for p in index.passages(q, limit=limit):
            key = (p["id"], p["start"])
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out[:limit]


def ask_library(index, question: str, history: list[tuple[str, str]] | None = None,
                cfg: config.Config | None = None, language: str = "es") -> tuple[str, list[dict]]:
    """(answer with [n] citations, the passages numbered from 1)."""
    found = find_passages(index, searches(question, cfg))
    if not found:
        return "", []
    blocks = []
    for n, p in enumerate(found, 1):
        try:
            when = datetime.fromisoformat(p["created"]).strftime("%Y-%m-%d")
        except ValueError:
            when = p["created"]
        who = f", {p['speaker']}" if p["speaker"] else ""
        blocks.append(f"[{n}] {p['title']} ({when}, at {export.stamp(p['start'])}{who}):\n{p['text']}")
    user = "Passages:\n\n" + "\n\n".join(blocks) + f"\n\n{_history(history or [])}Question: {question}"
    answer = llm.complete(LIBRARY_PROMPT.format(language=summary.LANGUAGES.get(language, language)), user, cfg)
    return answer, found


def link_times(answer: str, rid: str) -> str:
    """[m:ss] as Markdown links the view opens: play the recording from there."""
    return _STAMP.sub(lambda m: f"[{m.group(1)}](echo:{rid}@{seconds(m.group(1)):g})", answer)


def link_refs(answer: str, passages: list[dict]) -> str:
    """[n] (or [n, m]) as links to the passages' recordings and times."""
    def one(n: str) -> str:
        k = int(n) - 1
        if not 0 <= k < len(passages):
            return n
        p = passages[k]
        return f"[{n}](echo:{p['id']}@{p['start']:g})"

    return _REF.sub(lambda m: "[" + ", ".join(one(n.strip()) for n in m.group(1).split(",")) + "]", answer)


def parse_link(url: str) -> tuple[str, float] | None:
    """echo:ID@SECONDS -> (id, seconds)."""
    if not url.startswith("echo:") or "@" not in url:
        return None
    rid, _, at = url[5:].rpartition("@")
    try:
        return rid, float(at)
    except ValueError:
        return None
