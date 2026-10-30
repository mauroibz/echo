"""Summaries being made: one at a time, asked for by the user or started when a transcript is ready.

The window's Summary view and the automatic summaries share this queue, so a recording is never
summarized twice at once and the view shows what is waiting. Requests run off the window's
thread; one at a time, because a local server serves one request at a time anyway and a cloud
provider's rate limits are per account.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from echo_app.ui.common import run_task

from . import config, summary


class Summarizer(QObject):
    changed = Signal(str)  # a recording's summary state changed (queued, started, done, failed)
    progress = Signal(str, int, int)  # recording id, requests done, requests in all
    failed = Signal(str, str)  # recording id, why

    def __init__(self, library):
        super().__init__()
        self.library = library
        self._queue: list[str] = []
        self._running: str | None = None
        # Automatic summaries that failed, with the text they were made from: not tried again on
        # their own until the transcript changes (pressing Summarize always tries).
        self._failures: dict[str, tuple[str, str]] = {}

    def state(self, rid: str) -> str | None:
        """"running", "queued", or None."""
        if rid == self._running:
            return "running"
        return "queued" if rid in self._queue else None

    def failure(self, rid: str) -> str | None:
        f = self._failures.get(rid)
        return f[1] if f else None

    def request(self, rid: str) -> None:
        """The user pressed Summarize: ahead of the automatic ones."""
        self._failures.pop(rid, None)
        if self.state(rid):
            return
        self._queue.insert(0, rid)
        self.changed.emit(rid)
        self._next()

    def transcript_ready(self, rid: str) -> None:
        """A transcript was written: summarize it if the user wants that and it is not done yet."""
        cfg = config.load()
        if not (cfg.enabled and cfg.auto_summarize) or self.state(rid):
            return
        rec = self.library.get(rid)
        text = summary.source_text(rec) if rec is not None else ""
        if not text:
            return
        data = summary.load(rec)
        if data is not None and not summary.stale(rec, data):
            return
        f = self._failures.get(rid)
        if f and f[0] == summary.source_sha(rec):
            return
        self._queue.append(rid)
        self.changed.emit(rid)
        self._next()

    def _next(self):
        if self._running or not self._queue:
            return
        rid = self._running = self._queue.pop(0)
        self.changed.emit(rid)
        rec = self.library.get(rid)

        def work(progress):
            if rec is None:
                raise ValueError("the recording is gone")
            return summary.write(rec, progress=lambda d, t: progress((d, t)))

        def done(_data=None):
            self._running = None
            self._failures.pop(rid, None)
            self.changed.emit(rid)
            self._next()

        def error(msg):
            self._running = None
            if rec is not None:
                self._failures[rid] = (summary.source_sha(rec), msg)
            self.changed.emit(rid)
            self.failed.emit(rid, msg)
            self._next()

        run_task(work, on_done=done, on_error=error, on_progress=lambda v: self.progress.emit(rid, *v))
