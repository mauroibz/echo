"""Studio's window: Echo's window with a rail at the left (Record, then Briefing, Recordings, People).

Recordings is Echo's window exactly as it is, so turning Studio off or on never moves the user's
recordings. Record heads the rail, with the waveform Echo's Record wears, so a recording starts
from any page without going to the list of past ones; while it runs, the rail shows how long. The
rail shows once Studio has something to show (a summaries server or a calendar); until then the
window is Echo's.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QStackedWidget, QToolButton, QVBoxLayout,
                               QWidget)

from echo_app.ui import theme
from echo_app.ui.common import fmt_duration
from echo_app.ui.main_window import MainWindow

RAIL_W = 76


class Rail(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("studioRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(RAIL_W)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(14, 20, 14, 20)
        self.lay.setSpacing(10)
        self.top = QVBoxLayout()
        self.top.setSpacing(10)
        self.lay.addLayout(self.top)
        self.lay.addStretch(1)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._style()

    def _style(self):
        t = self._tokens = theme.current()
        self.setStyleSheet(f"""
            QWidget#studioRail {{ background: {t.deep_top}; }}
            QWidget#studioRail QToolButton {{ border: none; border-radius: 14px; padding: 0; background: transparent; }}
            QWidget#studioRail QToolButton:hover {{ background: {theme.rgba('on_deep', 0.10)}; }}
            QWidget#studioRail QToolButton:checked {{ background: {t.accent}; }}
            QWidget#studioRail QToolButton#railRecord {{ background: {t.coral}; border-radius: 24px; }}
            QWidget#studioRail QToolButton#railRecord:hover {{ background: #ff8a8a; }}
            QWidget#studioRail QToolButton#railRecord[live="true"] {{ background: {t.coral_deep}; }}
            QWidget#studioRail QLabel#railClock {{ color: {t.coral}; background: transparent; }}
        """)

    def changeEvent(self, e):
        # Restyled when the theme changes; setting the style sheet sends another palette change,
        # so only a new set of tokens restyles.
        if e.type() == QEvent.Type.PaletteChange and self._tokens is not theme.current():
            self._style()
        super().changeEvent(e)

    def add(self, ic: str, tip: str) -> QToolButton:
        b = QToolButton()
        b.setCheckable(True)
        b.setIcon(theme.tinted(ic, "on_deep"))
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(48, 48)
        b.setToolTip(tip)
        b.setAccessibleName(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.group.addButton(b)
        self.top.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        return b

    def add_record(self) -> QToolButton:
        """Record, at the head of the rail above the pages, with the clock under it."""
        b = QToolButton()
        b.setObjectName("railRecord")
        b.setIcon(theme.tinted("audio-lines", "on_accent"))
        b.setIconSize(QSize(22, 22))
        b.setFixedSize(48, 48)
        b.setToolTip("Record (Ctrl+R)")
        b.setAccessibleName("Record")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lay.insertWidget(0, b, 0, Qt.AlignmentFlag.AlignHCenter)
        self.clock = QLabel()
        self.clock.setObjectName("railClock")
        self.clock.setFont(theme.display_font(0.78, QFont.Weight.ExtraBold))
        self.clock.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.clock.hide()
        self.lay.insertWidget(1, self.clock, 0, Qt.AlignmentFlag.AlignHCenter)
        self.lay.insertSpacing(2, 14)  # apart from the pages: an action, not a place
        return b


class StudioWindow(MainWindow):
    """Echo's window inside Studio's rail. `add_page` adds a page with its rail button; the
    recordings page is Echo's own layout."""

    def _build_layout(self):
        super()._build_layout()
        self.recordings_page = self.takeCentralWidget()  # taken, not replaced: setCentralWidget deletes it
        root = QWidget()
        root.setObjectName("studioRoot")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.rail = Rail()
        h.addWidget(self.rail)
        self.pages = QStackedWidget()
        h.addWidget(self.pages, 1)
        self._page_buttons: dict[str, tuple[QToolButton, QWidget]] = {}
        self.setCentralWidget(root)
        self.pages.addWidget(self.recordings_page)
        self.rail.hide()

    def add_page(self, key: str, title: str, ic: str, widget: QWidget, shortcut: str | None = None,
                 first: bool = False) -> QToolButton:
        b = self.rail.add(ic, f"{title} ({shortcut})" if shortcut else title)
        if first:  # Home goes above the pages added before it
            self.rail.top.insertWidget(0, self.rail.top.takeAt(self.rail.top.count() - 1).widget(),
                                       0, Qt.AlignmentFlag.AlignHCenter)
        if widget is not self.recordings_page:
            self.pages.addWidget(widget)
        self._page_buttons[key] = (b, widget)
        b.clicked.connect(lambda _c=False, k=key: self.show_page(k))
        if shortcut:
            QShortcut(QKeySequence(shortcut), self, activated=lambda k=key: self.show_page(k))
        return b

    def show_page(self, key: str):
        b, w = self._page_buttons.get(key, (None, self.recordings_page))
        if b is not None:
            b.setChecked(True)
        self.pages.setCurrentWidget(w)

    def page(self) -> str | None:
        w = self.pages.currentWidget()
        return next((k for k, (_b, pw) in self._page_buttons.items() if pw is w), None)

    def set_rail(self, on: bool, home: str | None = "home"):
        """Show the rail (Studio set up) on Home, or hide it and show Echo's window alone."""
        if on == self.rail.isVisible():
            return
        self.rail.setVisible(on)
        if on and home in self._page_buttons:
            self.show_page(home)
        elif not on:
            self.pages.setCurrentWidget(self.recordings_page)

    def show_recording(self, rid: str, at: float | None = None):
        self.show_page("recordings")
        super().show_recording(rid, at)

    def open_profile_dialog(self, name: str | None = None):
        """Echo's People window (aliases, tags, voice), whatever the rail."""
        MainWindow.open_people(self, name)

    def open_people(self, name: str | None = None):
        """People from a speaker's name or the menu: Studio's page when the rail is on."""
        screen = self._page_buttons.get("people", (None, None))[1]
        if self.rail.isVisible() and screen is not None and name:
            self.show_page("people")
            screen.select(name)
            return
        super().open_people(name)

    def _recording_started(self, rid: str):
        super()._recording_started(rid)
        self._mark_live(True)

    def _recording_stopped(self, rid: str):
        super()._recording_stopped(rid)
        self._mark_live(False)

    def _mark_live(self, on: bool):
        b = getattr(self, "rail_record", None)
        if b is None:
            return
        theme.set_role(b, live=on)
        b.setIcon(theme.tinted("square" if on else "audio-lines", "on_accent"))
        b.setToolTip("Stop recording (Ctrl+R)" if on else "Record (Ctrl+R)")
        b.setAccessibleName("Stop recording" if on else "Record")
        if not hasattr(self, "_rail_tick"):
            self._rail_tick = QTimer(self)
            self._rail_tick.timeout.connect(self._update_rail_clock)
        self.rail.clock.setVisible(on)
        if on:
            self.rail.clock.setText("0:00")
            self._rail_tick.start(1000)
        else:
            self._rail_tick.stop()

    def _update_rail_clock(self):
        sess = self.recorder_panel.session
        if sess is None:
            return
        try:
            self.rail.clock.setText(fmt_duration(sess.status().get("elapsed", 0)))
        except Exception:  # noqa: BLE001 - a status read racing the stop
            pass
