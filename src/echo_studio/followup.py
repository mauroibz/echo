"""A follow-up email drafted from a summary and its action items (stdlib only). Studio sends nothing:
the draft is copied or handed to the user's mail program through a mailto: link."""

from __future__ import annotations

from urllib.parse import quote

from echo_app.library import Recording

from . import actions, config, llm, summary

PROMPT = """You write the follow-up email after a meeting, from its summary and action items.
In {language}, short and plain: a greeting to the group, two to four sentences on what was agreed, then the
action items as a list with who does what and by when, and a one-line close. No subject line in
the body, no placeholders such as [Name], no sign-off name. First line: "Subject: " and a subject
of at most 8 words; then an empty line; then the body."""


def draft(rec: Recording, cfg: config.Config | None = None) -> tuple[str, str]:
    """(subject, body) for the recording's summary; raises ValueError without a summary."""
    data = summary.load(rec)
    if data is None:
        raise ValueError("summarize this recording first")
    lang = data.get("language") or summary.language(rec)
    user = f"Meeting: {rec.meta.title}\n\nSummary:\n\n{data['text']}"
    items = (actions.load(rec) or {}).get("items", [])
    if items:
        lines = [f"- {i['text']}" + (f" ({i['owner']})" if i.get("owner") else "")
                 + (f", by {i['due']}" if i.get("due") else "") for i in items if not i.get("discarded")]
        user += "\n\nAction items:\n" + "\n".join(lines)
    reply = llm.complete(PROMPT.format(language=summary.LANGUAGES.get(lang, lang)), user, cfg).strip()
    subject, body = "", reply
    first, _, rest = reply.partition("\n")
    if first.lower().startswith(("subject:", "asunto:")):
        subject, body = first.split(":", 1)[1].strip(), rest.strip()
    return subject or rec.meta.title, body


def mailto(subject: str, body: str) -> str:
    return f"mailto:?subject={quote(subject)}&body={quote(body)}"
