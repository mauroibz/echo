"""Settings, Calendar: the private ICS addresses Studio reads, and whether it records the meetings."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from echo_app import settings
from echo_app.ui import theme
from echo_app.ui.common import run_task

from . import calendar, config, keychain


def _dim(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    theme.set_role(lbl, dim=True)
    return lbl


class CalendarPage(QWidget):
    def __init__(self, on_saved=None):
        super().__init__()
        self.on_saved = on_saved
        lay = QVBoxLayout(self)
        lay.addWidget(_dim("Paste your calendar's private address in iCal format, one per line. Google Calendar: "
                           "Settings, your calendar, “Secret address in iCal format”. Outlook / Teams: "
                           "Settings, Calendar, Shared calendars, “Publish a calendar”, the ICS link. Echo "
                           "only reads it, keeps the address in your keyring, and shows the next meeting, "
                           "names recordings after their meeting and gives the summary its invitation."))
        self.urls = QPlainTextEdit()
        self.urls.setAccessibleName("Calendar addresses")
        self.urls.setPlaceholderText("https://calendar.google.com/calendar/ical/…/basic.ics")
        self.urls.setFixedHeight(self.urls.fontMetrics().lineSpacing() * 4 + 16)
        self.from_env = bool(os.environ.get(calendar.URLS_ENV))
        self.no_keyring = not self.from_env and not keychain.available()
        if self.from_env or self.no_keyring:
            self.urls.setEnabled(False)
            self.urls.setPlaceholderText(f"Taken from ${calendar.URLS_ENV}" if self.from_env
                                         else f"No keyring: set ${calendar.URLS_ENV}")
        else:
            self.urls.setPlainText("\n".join(calendar.urls()))
        lay.addWidget(self.urls)
        row = QHBoxLayout()
        self.test_btn = QPushButton("Test")
        self.test_btn.clicked.connect(self.test)
        row.addWidget(self.test_btn)
        self.result = _dim()
        row.addWidget(self.result, 1)
        lay.addLayout(row)
        self.record = QCheckBox("Record the meetings that have a video link when they start")
        self.record.setChecked(config.load().auto_record)
        self.record.setToolTip("Stops 10 minutes after the meeting ends unless you stopped it. The home says "
                               "beforehand, with Skip.")
        self.record.toggled.connect(self._explain)
        lay.addWidget(self.record)
        self.note = _dim()
        lay.addWidget(self.note)
        lay.addStretch(1)
        self._explain()

    def _explain(self):
        bg = settings.load()[0].background
        self.note.setText("" if not self.record.isChecked() or bg else
                          "Echo has to be running when a meeting starts: turn on “Keep Echo running in the "
                          "tray, and start it when you log in” in General.")
        self.note.setVisible(bool(self.note.text()))

    def test(self):
        text = self.urls.toPlainText()
        found = calendar._clean(text) if not self.from_env else calendar.urls()
        if not found:
            self.result.setText("Paste an address that starts with https:// first.")
            return
        self.result.setText("Reading the calendar…")
        self.test_btn.setEnabled(False)

        def go():
            from datetime import datetime, timedelta

            from . import ics

            now = datetime.now().astimezone()
            n, errors = 0, []
            for u in found:
                try:
                    n += sum(1 for e in ics.parse(calendar.fetch(u), now, now + timedelta(days=7)) if not e.all_day)
                except (OSError, ValueError) as e:
                    errors.append(str(e))
            return n, errors

        def done(result):
            n, errors = result
            self.test_btn.setEnabled(True)
            self.result.setText("; ".join(errors) if errors else
                                f"It works: {n} meeting{'s' if n != 1 else ''} in the next 7 days.")

        def failed(msg):
            self.test_btn.setEnabled(True)
            self.result.setText(f"Not read: {msg}")

        run_task(go, on_done=done, on_error=failed)

    def apply(self):
        if not (self.from_env or self.no_keyring):
            text = self.urls.toPlainText()
            bad = [ln for ln in text.split() if ln and not calendar._clean(ln)]
            if bad:
                raise ValueError(f"not a calendar address: {bad[0][:60]}")
            try:
                calendar.save_urls(text)
            except keychain.KeychainError as e:
                raise ValueError(str(e)) from None
        cfg = config.load()
        cfg.auto_record = self.record.isChecked()
        config.save(cfg)
        if self.on_saved:
            self.on_saved()
