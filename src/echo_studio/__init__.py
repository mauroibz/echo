"""Echo Studio: what Echo leaves out because it needs a language model or a cloud service.

An extension of Echo (see echo_app/extensions.py): installed next to it, it adds to the same app,
and Echo never imports it. It adds minutes (summaries and action items) from a language-model
server, and the user's calendar: the next meeting, each recording's event, and the meetings
recorded when they start. Nothing is sent anywhere until a server is set up in Settings,
Summaries; then each transcript is summarized when it is ready, unless the user turned that off.
The calendar is only read, from the private addresses set in Settings, Calendar.
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
_jobs = None
_meetings = None


def settings_pages() -> list:
    from .calendar_ui import CalendarPage
    from .ui import SettingsPage

    return [("Summaries", SettingsPage(on_saved=_offer_view)),
            ("Calendar", CalendarPage(on_saved=lambda: _meetings.start() if _meetings is not None else None))]


def attach_window(window) -> None:
    from .jobs import Summarizer
    from .meetings import Meetings

    global _window, _jobs, _meetings
    _window = window
    _jobs = Summarizer(window.library)
    _meetings = Meetings(window)
    _meetings.message.connect(window.show_message)
    window.transcribed.connect(_meetings.transcribed)  # first: the summary reads the event it saves
    window.transcribed.connect(_jobs.transcript_ready)
    _meetings.start()
    _offer_view()


def speaker_names(rec) -> list[str]:
    """The names to offer for a recording's speakers: who its calendar event invited."""
    from . import calendar

    w = _window
    return calendar.attendee_names(w.library, rec) if w is not None else []


def _offer_view() -> None:
    """The Summary view and Studio's screens, once a server is set up (at start, or right after
    Settings)."""
    from .ask_ui import AskScreen, AskView
    from .ui import VIEW_TITLE, SummaryView

    w = _window
    if w is None or not config.enabled() or any(isinstance(v, SummaryView) for v in w.views.views()):
        return
    w.add_view(VIEW_TITLE, SummaryView(_jobs, message=w.show_message, show_recording=w.show_recording))
    w.add_view("Ask", AskView(w.show_recording))
    w.add_screen("Ask", "message-circle-question", AskScreen(w.library, w.show_recording), "Ctrl+Shift+A")


def person_sections(name: str) -> list:
    from .actions_ui import person_section

    w = _window
    if w is None or not config.enabled():
        return []
    return [("Action items", person_section(w.library, name, w.show_recording))]
