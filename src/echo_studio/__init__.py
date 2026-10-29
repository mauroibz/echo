"""Echo Studio: what Echo leaves out because it needs a language model or a cloud service.

An extension of Echo (see echo_app/extensions.py): installed next to it, it adds to the same app,
and Echo never imports it. So far it adds summaries from an OpenAI-compatible server. Nothing is
sent anywhere until a server is set up in Settings, Summaries, and then only when the user asks
for a summary.
"""

from __future__ import annotations

from . import config


def register_cli(sub) -> None:
    from . import cli

    cli.register(sub)


def doctor_checks() -> list:
    from echo_app.doctor import FAIL, OK, WARN, Check

    from . import llm

    cfg = config.load()
    if not cfg.enabled:
        return []
    name = f"Summaries server ({config.host(cfg.llm_url)})"
    try:
        names = llm.models(cfg)
    except llm.LLMError as e:
        return [Check(name, FAIL, str(e), "Check the address and key in Settings, Summaries, and that the "
                                          "server is running.")]
    if names and cfg.llm_model not in names:
        return [Check(name, WARN, f"answers, but has no model “{cfg.llm_model}”",
                      "It has: " + ", ".join(names[:8]) + ("…" if len(names) > 8 else ""))]
    return [Check(name, OK, f"answers; model {cfg.llm_model}")]


def markdown_sections(rec) -> list[tuple[str, str]]:
    from . import summary

    data = summary.load(rec)
    return [(summary.heading(rec), summary.demoted(data["text"]))] if data else []


_window = None


def settings_pages() -> list:
    from .ui import SettingsPage

    return [("Summaries", SettingsPage(on_saved=_offer_view))]


def attach_window(window) -> None:
    global _window
    _window = window
    _offer_view()


def _offer_view() -> None:
    """The Summary view, once a server is set up (at start, or right after Settings)."""
    from .ui import VIEW_TITLE, SummaryView

    w = _window
    if w is None or not config.enabled() or any(isinstance(v, SummaryView) for v in w.views.views()):
        return
    w.add_view(VIEW_TITLE, SummaryView(message=w.show_message))
