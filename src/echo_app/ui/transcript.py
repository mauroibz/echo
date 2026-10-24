"""Transcript panel: state views, the autosaving editor, find, follow-along."""

from __future__ import annotations

import logging
import os
import unicodedata

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QKeySequence, QMouseEvent, QPainter, QTextCharFormat,
                           QTextCursor)
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QTextEdit, QToolButton,
                               QVBoxLayout, QWidget)

from .. import align, dictionary, export, features, models, recorder, settings, transcription
from ..library import (CORRECTED, EDITED, NEEDS_FINALIZE, READY, RECORDING, T_FAILED, T_QUEUED, T_RUNNING,
                       TRANSCRIPT, Library, Recording)
from . import theme
from .common import fmt_date, fmt_duration, fmt_eta, icon, run_task

log = logging.getLogger(__name__)

AUTOSAVE_MS = 1000
# Block states marking a linked set's fixed lines: the part's heading, a line saying why it has no
# text yet, and the blank line between parts. Body lines carry no state.
HEAD, LOCK, SEP = 100_000, 200_000, 300_000
REPLAY_AFTER_MS = 1000  # after this long without typing, the passage being corrected plays again


def _fold(text: str) -> str:
    """Lower-case, accent-free copy with the same length (for accent-insensitive find)."""
    return "".join((unicodedata.normalize("NFD", c)[0] if c else c).lower() for c in text)


def _occurrences(hay: str, needle: str) -> list[tuple[int, int]]:
    out, i = [], hay.find(needle)
    while i >= 0:
        out.append((i, i + len(needle)))
        i = hay.find(needle, i + 1)
    return out


def segment_spans(segments: list[dict]) -> list[tuple[int, int, float]]:
    """Character spans of each passage in the joined model text (mirrors planning.join_text)."""
    spans = []
    pos = 0
    first = True
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if not first:
            pos += 2 if seg.get("paragraph") else 1
        spans.append((pos, pos + len(text), float(seg.get("start", 0.0))))
        pos += len(text)
        first = False
    return spans


def _estimate(duration: float | None) -> str:
    """", in about 4 minutes" from the measured speed, for recordings long enough to wait for."""
    minutes, _measured = transcription.minutes_per_hour()
    if not duration or minutes is None:
        return ""
    est = duration / 3600 * minutes
    if est < 1:
        return ""
    return f", in about {round(est)} minute{'s' if round(est) != 1 else ''}"


def flag_reason(flag: str, seg: dict) -> str:
    """Why a passage is marked, in words."""
    seconds = max(0, round(float(seg.get("end", 0)) - float(seg.get("start", 0))))
    return {"short": f"very few words for {seconds} s of speech",
            "retried": "transcribed a second time because the first try came back too short",
            "low": "the model was unsure of it"}.get(flag, flag)


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def segment_offsets(segments: list[dict], language: str = "es") -> dict[int, int]:
    """Character offset of each non-empty segment in the joined text, by segment index."""
    sep = align.separator(language)
    out = {}
    pos = 0
    first = True
    for k, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if not first:
            pos += 2 if seg.get("paragraph") else sep
        # Edit positions refer to the unstripped segment text; the joined text is stripped.
        out[k] = pos - (len(seg.get("text") or "") - len((seg.get("text") or "").lstrip()))
        pos += len(text)
        first = False
    return out


def shown_segments(rec: Recording) -> list[dict]:
    """The model segments with the corrected texts when a corrected copy exists."""
    t = rec.transcript() or {}
    segs = t.get("segments", [])
    c = rec.corrected()
    if c and len(c.get("segments", [])) == len(segs):
        segs = [{**s, "text": tx} for s, tx in zip(segs, c["segments"])]
    return segs


class TimestampMargin(QWidget):
    """The editor's left margin: passage start times, and a dot where a marker falls."""

    DOT = 14  # width of the marker column
    LABEL_MAX = 120  # widest speaker name before it is elided

    def __init__(self, editor: "Editor"):
        super().__init__(editor)
        self.editor = editor
        self.stamps: list[tuple[int, float]] = []  # character position, seconds
        self.marks: list[tuple[int, dict]] = []  # character position of the passage, marker
        self.labels: list[tuple[int, str, str, int]] = []  # position, speaker name, color role, number
        self.setFont(theme.display_font(0.82, QFont.Weight.DemiBold, tabular=True))
        self.setMouseTracking(True)

    def _label_width(self) -> int:
        if not self.labels:
            return 0
        fm = self.fontMetrics()
        return min(self.LABEL_MAX, max(fm.horizontalAdvance(t) for _p, t, _c, _n in self.labels)) + 12

    def width_needed(self) -> int:
        w = (self.DOT if self.marks else 0) + self._label_width()
        if self.stamps:
            longest = max((export.stamp(t) for _p, t in self.stamps), key=len, default="0:00")
            w += self.fontMetrics().horizontalAdvance(longest) + 14
        return w + 4

    def _rect_of(self, pos: int):
        doc = self.editor.document()
        cur = QTextCursor(doc)
        cur.setPosition(min(pos, doc.characterCount() - 1))
        return self.editor.cursorRect(cur)

    def _dots(self):
        """(rect, marker) for each marker dot on screen."""
        out = []
        for pos, m in self.marks:
            r = self._rect_of(pos)
            if -r.height() < r.top() < self.height():
                out.append((QRect(2, r.top() + (r.height() - 9) // 2, 9, 9), m))
        return out

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme.current()
        p.setPen(QColor(t.muted))
        line = self.editor.fontMetrics().height()
        last_y = None
        dot = self.DOT if self.marks else 0
        label_w = self._label_width()
        left = dot + label_w
        fm = self.fontMetrics()
        for pos, text, role, _n in self.labels:
            r = self._rect_of(pos)
            if r.bottom() < 0 or r.top() > self.height():
                continue
            p.setPen(theme.color(role))
            p.drawText(QRect(dot, r.top(), label_w - 8, r.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(text, Qt.TextElideMode.ElideRight, label_w - 8))
        p.setPen(QColor(t.muted))
        for pos, sec in self.stamps:
            r = self._rect_of(pos)
            if r.bottom() < 0:
                continue
            if r.top() > self.height():
                break
            if last_y is not None and r.top() < last_y + line * 0.8:
                continue  # two passages start on one line: the first one's time is enough
            p.drawText(QRect(left, r.top(), self.width() - left - 10, r.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, export.stamp(sec))
            last_y = r.top()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.coral_deep))
        for rect, _m in self._dots():
            p.drawEllipse(rect)
        p.end()

    def _dot_at(self, pt):
        return next((m for rect, m in self._dots() if rect.adjusted(-3, -3, 3, 3).contains(pt)), None)

    def _label_at(self, pt):
        dot = self.DOT if self.marks else 0
        if not self.labels or not dot <= pt.x() < dot + self._label_width():
            return None
        for pos, _text, _role, n in self.labels:
            r = self._rect_of(pos)
            if r.top() <= pt.y() <= r.bottom():
                return n
        return None

    def mouseMoveEvent(self, e):
        m = self._dot_at(e.position().toPoint())
        speaker = self._label_at(e.position().toPoint())
        self.setCursor(Qt.CursorShape.PointingHandCursor if m or speaker else Qt.CursorShape.ArrowCursor)
        if speaker is not None:
            from PySide6.QtWidgets import QToolTip

            QToolTip.showText(e.globalPosition().toPoint(), "Click to name this speaker", self)
        if m:
            from PySide6.QtWidgets import QToolTip

            QToolTip.showText(e.globalPosition().toPoint(),
                              f"Marker at {export.stamp(m['at'])}" + (f": {m['note']}" if m.get("note") else "")
                              + "\nClick to play from here", self)

    def mousePressEvent(self, e):
        m = self._dot_at(e.position().toPoint())
        if m:
            self.editor.marker_clicked.emit(float(m["at"]))
            return
        n = self._label_at(e.position().toPoint())
        if n is not None:
            self.editor.speaker_clicked.emit(n, e.globalPosition().toPoint())


class Editor(QPlainTextEdit):
    ctrl_clicked = Signal(int)  # character position
    heading_clicked = Signal(int)  # a linked set's part number (from 0)
    marker_clicked = Signal(float)  # seconds
    speaker_clicked = Signal(int, object)  # speaker number, global position
    MAX_TEXT_WIDTH_CHARS = 90

    def __init__(self, parent=None):
        super().__init__(parent)
        self.menu_hook = None  # callable(menu, position) adding actions for the clicked spot
        self.tooltip_hook = None  # callable(position) -> tooltip text for that spot, or None
        self.key_hook = None  # called on every typing key, before the edit
        # A linked set: edit_guard(lo, hi) says whether the text between two positions may change
        # (False across or inside a part's heading); heading_at(pos) is the part whose heading is there.
        self.edit_guard = None
        self.heading_at = None
        self.margin = TimestampMargin(self)
        self.margin.hide()
        self.updateRequest.connect(lambda _r, _dy: self.margin.update())

    def set_stamps(self, stamps: list[tuple[int, float]] | None, marks: list[tuple[int, dict]] = (),
                   labels=()):
        """Show passage times (character position, seconds), marker dots and speaker names;
        nothing hides the margin."""
        self.margin.stamps = stamps or []
        self.margin.marks = list(marks)
        self.margin.labels = list(labels)
        if not self.margin.stamps and not self.margin.marks and not self.margin.labels:
            self.margin.hide()
            self.setViewportMargins(0, 0, 0, 0)
            return
        self.setViewportMargins(self.margin.width_needed(), 0, 0, 0)
        self._place_margin()
        self.margin.show()
        self.margin.update()

    def _place_margin(self):
        cr = self.contentsRect()
        self.margin.setGeometry(QRect(cr.left(), cr.top(), self.viewportMargins().left(), cr.height()))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_margin()

    def _edit_range(self, e) -> tuple[int, int] | None:
        """The text a key would change, or None for keys that change nothing (moving, copying)."""
        cur = self.textCursor()
        a, b = cur.selectionStart(), cur.selectionEnd()
        K, SK = Qt.Key, QKeySequence.StandardKey
        word_back = e.matches(SK.DeleteStartOfWord)
        word_fwd = e.matches(SK.DeleteEndOfWord) or e.matches(SK.DeleteEndOfLine)
        if e.matches(SK.Undo) or e.matches(SK.Redo) or e.matches(SK.Copy) or e.matches(SK.SelectAll):
            return None
        if e.matches(SK.Cut) or e.matches(SK.Paste):
            return a, b
        if e.key() in (K.Key_Backspace, K.Key_Delete) or word_back or word_fwd:
            if a != b:
                return a, b
            c = QTextCursor(cur)
            if word_back:
                c.movePosition(QTextCursor.MoveOperation.PreviousWord, QTextCursor.MoveMode.KeepAnchor)
            elif word_fwd:
                c.movePosition(QTextCursor.MoveOperation.EndOfWord if e.matches(SK.DeleteEndOfWord)
                               else QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                if c.position() == a:
                    c.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            elif e.key() == K.Key_Backspace:
                c.movePosition(QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.KeepAnchor)
            else:
                c.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            return min(c.position(), c.anchor()), max(c.position(), c.anchor())
        if e.text() and not (e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            return a, b  # typing (Enter and Tab too) replaces the selection
        return None

    def keyPressEvent(self, e):
        if self.edit_guard is not None:
            rng = self._edit_range(e)
            if rng is not None and not self.edit_guard(*rng):
                e.accept()  # the part's heading, or another part: nothing changes
                return
        if self.key_hook and e.text() and not (e.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                                                | Qt.KeyboardModifier.AltModifier)):
            self.key_hook()
        elif self.key_hook and e.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.key_hook()
        super().keyPressEvent(e)

    def insertFromMimeData(self, source):
        if self.edit_guard is not None:
            cur = self.textCursor()
            if not self.edit_guard(cur.selectionStart(), cur.selectionEnd()):
                return
        super().insertFromMimeData(source)

    def mousePressEvent(self, e: QMouseEvent):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier and e.button() == Qt.MouseButton.LeftButton:
            self.ctrl_clicked.emit(self.cursorForPosition(e.position().toPoint()).position())
            return
        if self.heading_at is not None and e.button() == Qt.MouseButton.LeftButton:
            k = self.heading_at(self.cursorForPosition(e.position().toPoint()).position())
            if k is not None:
                self.heading_clicked.emit(k)
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self.heading_at is not None and not e.buttons():
            k = self.heading_at(self.cursorForPosition(e.position().toPoint()).position())
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if k is not None
                                      else Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(e)

    def event(self, e):
        if e.type() == e.Type.ToolTip and self.tooltip_hook:
            from PySide6.QtWidgets import QToolTip

            pos = self.viewport().mapFromGlobal(e.globalPos())
            tip = self.tooltip_hook(self.cursorForPosition(pos).position())
            if tip:
                QToolTip.showText(e.globalPos(), tip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def contextMenuEvent(self, e):
        menu = self.createStandardContextMenu(e.pos())
        if self.edit_guard is not None:
            cur = self.textCursor()
            if not self.edit_guard(cur.selectionStart(), cur.selectionEnd()):
                for a in menu.actions():
                    if a.objectName() in ("edit-cut", "edit-paste", "edit-delete"):
                        a.setEnabled(False)
        if self.menu_hook:
            self.menu_hook(menu, self.cursorForPosition(e.pos()).position())
        menu.exec(e.globalPos())
        menu.deleteLater()


class StateView(QWidget):
    """Centered message with optional progress bar and buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self.glyph = QLabel()
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.glyph)
        self.headline = QLabel()
        self.headline.setFont(theme.display_font(1.35, QFont.Weight.ExtraBold))
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.headline.setWordWrap(True)
        lay.addWidget(self.headline)
        self.detail = QLabel()
        theme.set_role(self.detail, dim=True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.setOpenExternalLinks(True)
        lay.addWidget(self.detail)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(360)
        self.progress.setTextVisible(False)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.progress)
        row.addStretch(1)
        lay.addLayout(row)
        self.buttons = QHBoxLayout()
        self.buttons.addStretch(1)
        self._btn_end = QWidget()
        lay.addLayout(self.buttons)
        lay.addStretch(2)
        self._btns: list[QPushButton] = []

    def show_state(self, headline: str, detail: str = "", progress: float | None = None,
                   busy: bool = False, actions=(), glyph: str = "transcribe"):
        self.glyph.setPixmap(icon(glyph, "accent").pixmap(QSize(44, 44), self.devicePixelRatioF()))
        self.headline.setText(headline)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        if progress is None and not busy:
            self.progress.hide()
        else:
            self.progress.show()
            if progress is None:
                self.progress.setRange(0, 0)
            else:
                self.progress.setRange(0, 1000)
                self.progress.setValue(int(progress * 1000))
        for b in self._btns:
            self.buttons.removeWidget(b)
            b.deleteLater()
        self._btns = []
        # Remove the trailing stretch, add buttons, re-add stretch.
        while self.buttons.count():
            self.buttons.takeAt(0)
        self.buttons.addStretch(1)
        for label, ic, fn, default in actions:
            b = QPushButton(icon(ic), label)
            b.clicked.connect(fn)
            if default:
                b.setDefault(True)
                theme.set_role(b, primary=True)
            self.buttons.addWidget(b)
            self._btns.append(b)
        self.buttons.addStretch(1)


class SetPart:
    """One part of a linked set as laid out in the editor."""

    def __init__(self, rec: Recording, timeline_part, heading: str, state: str | None):
        self.rec = rec
        self.tl = timeline_part  # sets.Part: offset and crop on the set's timeline
        self.heading = heading
        self.state = state  # why there is no text yet; None when the part has text to edit
        self.loaded = ""  # the text shown when loaded or last saved
        self.sig = None


class TranscriptPanel(QWidget):
    seek_requested = Signal(float)
    part_requested = Signal(str)  # a linked set's part heading was clicked: show that recording
    message = Signal(str)
    download_requested = Signal()
    changed = Signal(str)  # recording id whose files changed
    timestamps_toggled = Signal(bool)
    marker_clicked = Signal(float)

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.library = library
        self.rec: Recording | None = None
        self.linked = None  # the LinkedSet shown instead of a recording
        self._parts: list[SetPart] = []
        self._loading = False
        self._spans: list[tuple[int, int, float]] = []
        self._corrections: list[tuple[int, int, dict]] = []  # absolute span and the logged edit
        self._candidate: dictionary.Candidate | None = None
        self._dict_version = None
        self._current_span = -1
        self._find_matches: list[tuple[int, int]] = []
        self._find_index = -1
        self._find_from_search = False
        self._shown_signature = None
        self._autosave = QTimer(self, singleShot=True, interval=AUTOSAVE_MS, timeout=self.save)
        # While typing, passage positions follow the text a moment later (alignment of the edit).
        self._realign = QTimer(self, singleShot=True, interval=400, timeout=self._align_now)
        self._segments: list[dict] = []
        self._flagged: list[tuple[int, int, dict]] = []
        self._passages: list[tuple[int, int, int]] = []  # (start, end, segment index) in the shown text
        self.player = None  # the PlayerPanel, for editing with the audio
        self._audio_k: int | None = None  # the passage playing (or paused by typing) for editing
        self._typing_paused = False
        self._replay = QTimer(self, singleShot=True, interval=REPLAY_AFTER_MS, timeout=self._replay_passage)
        self.show_timestamps = settings.load()[0].show_timestamps
        self._build()
        self.set_recording(None)

    # ---- layout ----
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.state = StateView()
        self.stack.addWidget(self.state)

        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(16, 12, 16, 10)
        pl.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.status = QLabel()
        self.status.setFont(theme.display_font(0.85, QFont.Weight.Bold))
        theme.set_role(self.status, dim=True)
        bar.addWidget(self.status, 1)

        def tool(text, ic, fn, tip):
            b = QToolButton()
            b.setText(text)
            b.setIcon(icon(ic))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            bar.addWidget(b)
            return b

        self.times_btn = tool("Times", "clock", lambda: self.set_show_timestamps(self.times_btn.isChecked()),
                              "Show passage start times in the margin (Ctrl+T)")
        self.times_btn.setCheckable(True)
        self.times_btn.setChecked(self.show_timestamps)
        self.copy_btn = tool("Copy", "copy", self.copy_all, "Copy the whole transcript (Ctrl+Shift+C)")
        self.export_btn = tool("Export…", "export", self.export_text,
                               "Save as text, Markdown, subtitles (SRT, VTT) or JSON (Ctrl+E)")
        self.more_btn = QToolButton()
        self.more_btn.setIcon(icon("more"))
        self.more_btn.setToolTip("More actions")
        self.more_btn.setAccessibleName("More actions")
        self.more_btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.more_btn)
        self.act_find = menu.addAction(icon("find"), "Find…  (Ctrl+F)", self.open_find)
        menu.addAction(icon("copy"), "Copy with timestamps  (Ctrl+Alt+C)", self.copy_with_timestamps)
        menu.addSeparator()
        self.act_retx = menu.addAction(icon("transcribe"), "Transcribe again", lambda: self.request(None))
        self.act_retx_base = menu.addAction("Transcribe again without the Spanish adapter", lambda: self.request(False))
        self.lang_menu = menu.addMenu(icon("languages"), "Language")
        self.act_speakers = menu.addAction(icon("users"), "Label speakers")
        self.act_speakers.setCheckable(True)
        self.act_speakers.setToolTip("Show who speaks when (off for monologues)")
        self.act_speakers.toggled.connect(lambda on: self.set_speakers_off(not on))
        self.lang_menu.aboutToShow.connect(self._fill_languages)
        self.act_revert = menu.addAction(icon("revert"), "Revert to model output…", self.revert)
        self.more_btn.setMenu(menu)
        bar.addWidget(self.more_btn)
        pl.addLayout(bar)

        self.notice = QFrame()
        self.notice.setObjectName("notice")
        nl = QHBoxLayout(self.notice)
        nl.setContentsMargins(12, 6, 8, 6)
        self.notice_text = QLabel()
        self.notice_text.setWordWrap(True)
        nl.addWidget(self.notice_text, 1)
        self.notice_progress = QProgressBar()
        self.notice_progress.setMaximumWidth(160)
        self.notice_progress.setTextVisible(False)
        nl.addWidget(self.notice_progress)
        self.notice_a = QPushButton()
        self.notice_b = QPushButton()
        self._notice_fn = {"a": None, "b": None}
        self.notice_a.clicked.connect(lambda: self._notice_fn["a"] and self._notice_fn["a"]())
        self.notice_b.clicked.connect(lambda: self._notice_fn["b"] and self._notice_fn["b"]())
        nl.addWidget(self.notice_a)
        nl.addWidget(self.notice_b)
        self.notice.hide()
        pl.addWidget(self.notice)

        self.editor = Editor()
        self.editor.setObjectName("editor")
        self.editor.setFrameShape(QFrame.Shape.NoFrame)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setTabChangesFocus(True)
        self.editor.setAccessibleName("Transcript")
        self.editor.setFont(theme.reading_font())
        self.editor.document().setDocumentMargin(14)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.ctrl_clicked.connect(self._on_ctrl_click)
        self.editor.marker_clicked.connect(self.marker_clicked.emit)
        self.editor.speaker_clicked.connect(self._speaker_menu)
        self.editor.heading_clicked.connect(lambda k: self.part_requested.emit(self._parts[k].rec.id)
                                            if 0 <= k < len(self._parts) else None)
        self.editor.document().contentsChange.connect(self._check_structure)
        # Centered reading column on wide windows, on a full-width text background.
        column = QWidget()
        cl = QHBoxLayout(column)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addStretch(1)
        self.editor.setMaximumWidth(self.editor.fontMetrics().averageCharWidth() * Editor.MAX_TEXT_WIDTH_CHARS + 60)
        cl.addWidget(self.editor, 100)
        cl.addStretch(1)
        pl.addWidget(column, 1)
        self.editor.menu_hook = self._menu_hook
        self.editor.key_hook = self._typing
        self.editor.tooltip_hook = self._tooltip

        # One dictionary suggestion at a time, offered after the save that produced it.
        self.chip = QFrame()
        self.chip.setObjectName("chip")
        chl = QHBoxLayout(self.chip)
        chl.setContentsMargins(12, 4, 6, 4)
        chl.setSpacing(6)
        self.chip_text = QLabel()
        self.chip_text.setTextFormat(Qt.TextFormat.RichText)
        chl.addWidget(self.chip_text, 1)
        self.chip_add = QPushButton(icon("ok"), "Add")
        self.chip_add.setToolTip("Spell it this way in new transcripts and fix it in existing ones")
        self.chip_add.clicked.connect(self._accept_candidate)
        chl.addWidget(self.chip_add)
        self.chip_no = QPushButton("Not this word")
        self.chip_no.setToolTip("Never suggest this word again")
        self.chip_no.clicked.connect(self._decline_candidate)
        chl.addWidget(self.chip_no)
        self.chip.hide()
        pl.addWidget(self.chip)

        self.findbar = QWidget()
        fl = QHBoxLayout(self.findbar)
        fl.setContentsMargins(0, 0, 0, 0)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find in transcript")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.textChanged.connect(self._find_update)
        self.find_edit.textEdited.connect(lambda _t: setattr(self, "_find_from_search", False))
        self.find_edit.returnPressed.connect(lambda: self._find_step(1))
        fl.addWidget(self.find_edit, 1)
        self.find_count = QLabel()
        fl.addWidget(self.find_count)
        prev_b = QToolButton(text="↑", toolTip="Previous (Shift+Enter)")
        prev_b.clicked.connect(lambda: self._find_step(-1))
        next_b = QToolButton(text="↓", toolTip="Next (Enter)")
        next_b.clicked.connect(lambda: self._find_step(1))
        close_b = QToolButton(text="✕", toolTip="Close (Esc)")
        close_b.clicked.connect(self.close_find)
        for b in (prev_b, next_b, close_b):
            fl.addWidget(b)
        self.findbar.hide()
        pl.addWidget(self.findbar)
        shift_enter = QAction(self.find_edit)
        shift_enter.setShortcut(QKeySequence("Shift+Return"))
        shift_enter.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        shift_enter.triggered.connect(lambda: self._find_step(-1))
        self.find_edit.addAction(shift_enter)
        esc = QAction(self.findbar)
        esc.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        esc.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.triggered.connect(self.close_find)
        self.findbar.addAction(esc)
        self.stack.addWidget(page)
        self.page = page

    # ---- selection and refresh ----
    def set_recording(self, rec: Recording | None):
        if self.linked is not None:
            self.save()
            self._leave_set()
        if self.rec is not None and (rec is None or rec.id != self.rec.id):
            self.save()
        switching = rec is None or self.rec is None or rec.id != self.rec.id
        self.rec = rec
        if switching:
            self._shown_signature = None
            self.close_find()
            self._replay.stop()
            self._audio_k, self._typing_paused = None, False
            self._offer([])
        self.refresh()

    def _signature(self, rec: Recording):
        def mt(name):
            try:
                return os.stat(rec.path(name)).st_mtime_ns
            except FileNotFoundError:
                return None
        return (rec.id, mt(TRANSCRIPT), rec.is_edited(), mt(CORRECTED))

    # ---- a linked set ----
    def _leave_set(self):
        self.linked, self._parts = None, []
        self.editor.edit_guard = self.editor.heading_at = None
        self.editor.setAcceptDrops(True)
        self._shown_signature = None
        self.close_find()
        self._replay.stop()
        self._audio_k, self._typing_paused = None, False
        self._offer([])
        self._loading = True
        self.editor.setPlainText("")
        self._loading = False
        for a in (self.act_retx, self.act_retx_base, self.lang_menu.menuAction(), self.act_speakers):
            a.setVisible(True)

    def set_linked(self, linked, parts: list[Recording]):
        """Show a linked set: its parts' transcripts one under the other, edited in place."""
        if self.linked is None or linked.id != self.linked.id:
            self.save()
            if self.linked is None:
                self.set_recording(None)
            else:
                self._leave_set()
            self.linked = linked
            self.editor.edit_guard = self._edit_allowed
            self.editor.heading_at = self._heading_at
            self.editor.setAcceptDrops(False)  # dragging text could carry it into another part
            for a in (self.act_retx, self.act_retx_base, self.lang_menu.menuAction(), self.act_speakers):
                a.setVisible(False)  # these act on one recording: select the part
        self.linked = linked
        self._set_parts = parts
        self.refresh()

    @staticmethod
    def _part_state(rec: Recording) -> str | None:
        if rec.meta.state == RECORDING:
            return "Recording in progress"
        if rec.meta.state != READY:
            return "Needs attention: select this part to repair it"
        if rec.is_edited() or rec.path(TRANSCRIPT).exists():
            return None
        st = rec.transcript_status()
        if st == T_RUNNING:
            p = rec.progress() or {}
            frac = (p.get("done", 0) / p["total"]) if p.get("total") else 0
            return f"Transcribing… {frac:.0%}"
        if st == T_QUEUED:
            return "Waiting to transcribe"
        if st == T_FAILED:
            return "Transcription failed: select this part to try again"
        return "Not transcribed yet: select this part to transcribe it"

    def _set_signature(self, parts: list[Recording]):
        return tuple((self._signature(r), self._part_state(r), r.meta.title, r.meta.speakers_off,
                      tuple(sorted(r.meta.speakers.items())), r.meta.crop_start, r.meta.crop_end) for r in parts)

    def _refresh_set(self):
        from .. import sets

        parts = [self.library.get(r.id) or r for r in self._set_parts]
        self._set_parts = parts
        self.stack.setCurrentWidget(self.page)
        self.notice.hide()
        sig = (self.linked.id, self._set_signature(parts))
        if sig == self._shown_signature:
            self._update_set_status()
            return
        if self._autosave.isActive():
            self.save()  # unsaved typing becomes the parts' edited text before anything reloads
            parts = [self.library.get(r.id) or r for r in parts]
            self._set_parts = parts
            sig = (self.linked.id, self._set_signature(parts))
        for r in parts:
            self._apply_dictionary(r)
        tl = sets.timeline(parts)
        self._parts = []
        for k, (r, part) in enumerate(zip(parts, tl)):
            length = f"  ·  {fmt_duration(part.length)}" if r.meta.duration else ""
            heading = f"{k + 1}  ·  {r.meta.title}  ·  {fmt_date(r.meta.created)}{length}"
            self._parts.append(SetPart(r, part, heading, self._part_state(r)))
        self._load_set_text()
        self._shown_signature = sig
        self._update_set_status()

    def _load_set_text(self):
        cur_pos = self.editor.textCursor().position()
        scroll = self.editor.verticalScrollBar().value()
        lines: list[tuple[str, int]] = []  # (text, block state); body text may hold several lines
        for k, part in enumerate(self._parts):
            if k:
                lines.append(("", SEP))
            lines.append((part.heading, HEAD + k))
            if part.state is not None:
                lines.append((part.state, LOCK + k))
            else:
                part.loaded = part.rec.text().rstrip("\n")
                lines.append((part.loaded, -1))
        self._loading = True
        doc = self.editor.document()
        doc.setUndoRedoEnabled(False)
        self.editor.setPlainText("\n".join(t for t, _s in lines))
        block = doc.begin()
        for text, state in lines:
            n = text.count("\n") + 1
            for _ in range(n):
                block.setUserState(state)
                block = block.next()
        t = theme.current()
        head_fmt = QTextCharFormat()
        head_fmt.setFontWeight(QFont.Weight.Bold)
        head_fmt.setForeground(QColor(t.accent_deep))
        lock_fmt = QTextCharFormat()
        lock_fmt.setFontItalic(True)
        lock_fmt.setForeground(QColor(t.muted))
        block = doc.begin()
        while block.isValid():
            st = block.userState()
            if HEAD <= st < SEP and block.length() > 1:
                c = QTextCursor(block)
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                c.setCharFormat(head_fmt if st < LOCK else lock_fmt)
            block = block.next()
        doc.setUndoRedoEnabled(True)
        self._loading = False
        c = self.editor.textCursor()
        c.setPosition(min(cur_pos, doc.characterCount() - 1))
        self.editor.setTextCursor(c)
        self.editor.verticalScrollBar().setValue(scroll)
        self._corrections = []
        self._current_span = -1
        self._align_now()

    def _bodies(self) -> list[tuple[int, int] | None]:
        """Each part's editable text as (start, end) positions; None for a part without text."""
        doc = self.editor.document()
        out: list[tuple[int, int] | None] = [None] * len(self._parts)
        k, start, end = -1, None, None
        block = doc.begin()

        def close():
            if 0 <= k < len(out) and start is not None and self._parts[k].state is None:
                out[k] = (start, end)

        while block.isValid():
            st = block.userState()
            if HEAD <= st < LOCK:
                close()
                k, start, end = st - HEAD, None, None
            elif st >= LOCK:
                pass
            else:
                if start is None:
                    start = block.position()
                end = block.position() + block.length() - 1
            block = block.next()
        close()
        return out

    def _edit_allowed(self, lo: int, hi: int) -> bool:
        return any(b is not None and b[0] <= lo and hi <= b[1] for b in self._bodies())

    def _heading_at(self, pos: int) -> int | None:
        block = self.editor.document().findBlock(pos)
        st = block.userState()
        return st - HEAD if HEAD <= st < LOCK else None

    def _structure_ok(self) -> bool:
        heads = []
        block = self.editor.document().begin()
        while block.isValid():
            if HEAD <= block.userState() < LOCK:
                heads.append(block.text())
            block = block.next()
        return heads == [p.heading for p in self._parts]

    def _check_structure(self, _pos, _removed, _added):
        """The last guard: an edit that reached a heading anyway (an input method, a drop) is undone."""
        if self.linked is None or self._loading or self._structure_ok():
            return
        QTimer.singleShot(0, self._restore_structure)

    def _restore_structure(self):
        if self.linked is None or self._structure_ok():
            return
        self.editor.undo()
        if not self._structure_ok():
            self._shown_signature = None
            self._refresh_set()
        self.message.emit("Each part's heading stays as it is; edit the text under it.")

    def _part_text(self, k: int, bodies=None) -> str | None:
        bodies = self._bodies() if bodies is None else bodies
        b = bodies[k]
        if b is None:
            return None
        c = QTextCursor(self.editor.document())
        c.setPosition(b[0])
        c.setPosition(b[1], QTextCursor.MoveMode.KeepAnchor)
        return c.selection().toPlainText()

    def _save_set(self):
        if not self._structure_ok():
            self.message.emit("Not saved: a part's heading changed. The text is shown again as saved.")
            self._shown_signature = None
            self._refresh_set()
            return
        bodies = self._bodies()
        for k, part in enumerate(self._parts):
            text = self._part_text(k, bodies)
            if text is None or text == part.loaded:
                continue
            rec = part.rec
            try:
                if text == rec.base_text().rstrip("\n"):
                    if rec.is_edited():
                        rec.revert_edits()
                else:
                    rec.save_edited(text)
            except OSError as e:
                self.message.emit(f"Could not save your edits: {e}")
                return
            part.loaded = text
            self.changed.emit(rec.id)
            if rec.is_edited():
                self._learn_from(rec, text)
        self._shown_signature = (self.linked.id, self._set_signature([p.rec for p in self._parts]))
        self._update_set_status()

    def _update_set_status(self):
        edited = sum(1 for p in self._parts if p.rec.is_edited())
        waiting = sum(1 for p in self._parts if p.state is not None)
        bits = [f"{len(self._parts)} parts"]
        if edited:
            bits.append(f"{edited} edited")
        if waiting:
            bits.append(f"{waiting} without text yet")
        self.status.setText(" · ".join(bits))
        self.act_revert.setEnabled(False)
        self._update_flag_count()

    def _set_segments(self) -> list[dict]:
        """Every part's shown segments on the set's timeline, each knowing its part."""
        out = []
        for k, part in enumerate(self._parts):
            if part.state is not None:
                continue
            for sg in shown_segments(part.rec):
                out.append({**sg, "start": part.tl.to_set(float(sg.get("start", 0.0))),
                            "end": part.tl.to_set(float(sg.get("end", 0.0))), "_part": k})
        return out

    def _align_set(self):
        """Passage spans of every part, in document positions and set time."""
        text = self.editor.toPlainText()
        bodies = self._bodies()
        segs = self._set_segments()
        self._segments = segs
        passages, corrections = [], []
        self._correction_part = {}
        for k, part in enumerate(self._parts):
            b = bodies[k]
            if b is None:
                continue
            idx = [i for i, sg in enumerate(segs) if sg["_part"] == k]
            local = [segs[i] for i in idx]
            language = (part.rec.transcript() or {}).get("language", "es")
            body = text[b[0]:b[1]]
            if local:
                passages += [(b[0] + a, b[0] + e, idx[j]) for a, e, j in align.align(local, body, language) if e > a]
            if not part.rec.is_edited() and body == part.loaded:
                c = part.rec.corrected()
                if c:
                    offsets = segment_offsets(local, language)
                    for ed in c.get("edits", []):
                        base = offsets.get(ed.get("segment"))
                        if base is not None:
                            corrections.append((b[0] + base + ed["start"], b[0] + base + ed["end"], ed))
                            self._correction_part[id(ed)] = part.rec
        self._passages = passages
        self._spans = [(a, e, float(segs[k].get("start", 0.0))) for a, e, k in passages]
        self._flagged = [(a, e, segs[k]) for a, e, k in passages
                         if segs[k].get("flags") and text[a:e].strip() == (segs[k].get("text") or "").strip()]
        self._corrections = corrections
        self._update_margin()
        self._apply_selections()
        self._update_flag_count()

    def refresh(self):
        """Re-evaluate what to show for the current recording (called on every library change)."""
        if self.linked is not None:
            self._refresh_set()
            return
        rec = self.rec
        if rec is None:
            self.stack.setCurrentWidget(self.state)
            self.state.show_state("No recording selected", "Select a recording on the left to see its transcript.", glyph="audio-lines")
            return
        rec = self.library.get(rec.id) or rec
        self.rec = rec
        st = rec.transcript_status()
        has_text = rec.is_edited() or rec.path(TRANSCRIPT).exists()
        if rec.meta.state == RECORDING:
            auto = features.auto_transcribe()
            self.stack.setCurrentWidget(self.state)
            self.state.show_state("Recording in progress",
                                  "The transcript will be created when you stop." if auto
                                  else "You can transcribe it after you stop.", glyph="mic")
            return
        if rec.meta.state == NEEDS_FINALIZE:
            self.stack.setCurrentWidget(self.state)
            self.state.show_state("This recording needs attention",
                                  (rec.meta.error or "Saving did not complete.") +
                                  "\nThe raw audio is safe on disk.",
                                  actions=[("Try saving again", "ok", self._retry_finalize, True)], glyph="warning")
            return
        if rec.meta.state != READY:
            self.stack.setCurrentWidget(self.state)
            self.state.show_state(rec.meta.state.capitalize())
            return
        if has_text:
            self._show_editor(rec, st)
            return
        self.stack.setCurrentWidget(self.state)
        if st == T_RUNNING:
            p = rec.progress() or {}
            stage = p.get("stage")
            if stage in ("loading", "detecting", "speakers"):
                head = {"loading": "Loading the model…", "detecting": "Finding speech…",
                        "speakers": "Telling the speakers apart…"}[stage]
                self.state.show_state(head, rec.meta.title, busy=True,
                                      actions=[("Cancel", "cancel", self.cancel, False)])
            else:
                frac = (p.get("done", 0) / p["total"]) if p.get("total") else 0
                self.state.show_state(f"Transcribing… {frac:.0%}", fmt_eta(p.get("eta_s")).capitalize(), progress=frac,
                                      actions=[("Cancel", "cancel", self.cancel, False)])
        elif st == T_QUEUED:
            transcription.ensure_worker(self.library)
            self.state.show_state("Waiting to transcribe", "It will start after the recordings ahead of it.",
                                  busy=True, actions=[("Cancel", "cancel", self.cancel, False)])
        elif st == T_FAILED:
            err = rec.error_text() or "Unknown error."
            actions = [("Try again", "transcribe", lambda: self.request(None), True)]
            if "models download" in err or not models.all_cached():
                actions.insert(0, ("Download model…", "download", self.download_requested.emit, True))
            self.state.show_state("Transcription failed", err, actions=actions, glyph="error")
        else:
            if not features.transcription_installed():
                self.state.show_state("Transcription is not installed",
                                      "Install it from the Echo folder with:\n./install.sh --with-transcription",
                                      glyph="download")
            elif not models.all_cached():
                self.state.show_state("Not transcribed yet",
                                      "The transcription model needs to be downloaded once (about 4.3 GB).",
                                      actions=[("Download model…", "download", self.download_requested.emit, True)])
            else:
                dur = f" ({fmt_duration(rec.meta.duration)})" if rec.meta.duration else ""
                self.state.show_state("Not transcribed yet",
                                      f"Transcribe this recording{dur} on this computer{_estimate(rec.meta.duration)}.",
                                      actions=[("Transcribe", "transcribe", lambda: self.request(None), True)])

    def _show_editor(self, rec: Recording, st: str):
        self.stack.setCurrentWidget(self.page)
        if self._autosave.isActive() and self._shown_signature and self._shown_signature[0] == rec.id:
            self.save()  # unsaved typing becomes the edited text before anything reloads
        self._apply_dictionary(rec)
        sig = self._signature(rec)
        if sig != self._shown_signature and not (self.editor.hasFocus() and self._shown_signature
                                                 and self._shown_signature[0] == rec.id
                                                 and self._shown_signature[2] == sig[2] and rec.is_edited()):
            self._load_text(rec)
            self._shown_signature = sig
        self._update_status(rec)
        self._update_notice(rec, st)

    def _load_text(self, rec: Recording):
        self._loading = True
        text = rec.text()
        if self.editor.toPlainText() != text:
            self.editor.setPlainText(text)
        self._loading = False
        self._load_spans(rec)
        self._current_span = -1
        self._apply_selections()

    def _load_spans(self, rec: Recording):
        self._spans, self._corrections = [], []
        self._segments = shown_segments(rec)
        self._align_now()
        if rec.is_edited():
            return
        segs = self._segments
        c = rec.corrected()
        if c:
            offsets = segment_offsets(segs, (rec.transcript() or {}).get("language", "es"))
            for e in c.get("edits", []):
                base = offsets.get(e.get("segment"))
                if base is not None:
                    self._corrections.append((base + e["start"], base + e["end"], e))

    def _update_status(self, rec: Recording):
        t = rec.transcript() or {}
        when = fmt_date(t.get("created", "")) if t else ""
        model = "Spanish adapter" if (t.get("model") or {}).get("adapter_enabled") else "base model"
        if t.get("language", "es") != "es":
            model = models.language_name(t["language"])
        if rec.is_edited():
            self.status.setText("Edited" + (f" · model transcript from {when}" if when else ""))
        elif t:
            n = len((rec.corrected() or {}).get("edits", []))
            fixed = f" · {n} name{'s' if n != 1 else ''} corrected" if n else ""
            self.status.setText(f"Model transcript · {when} · {model}{fixed}")
        else:
            self.status.setText("")
        self.act_revert.setEnabled(rec.is_edited() and bool(t))
        installed = features.transcription_installed()
        self.act_retx.setEnabled(installed)
        self.act_retx_base.setEnabled(installed and transcription.language_of(rec) == "es")
        labeled = bool(t.get("speakers"))
        self.act_speakers.blockSignals(True)
        self.act_speakers.setChecked(not rec.meta.speakers_off)
        self.act_speakers.blockSignals(False)
        self.act_speakers.setEnabled(labeled or rec.meta.speakers_off)
        if labeled and not rec.meta.speakers_off and not rec.is_edited():
            n = int(t["speakers"].get("count", 0))
            self.status.setText(self.status.text() + f" · {n} speakers")
        self._update_flag_count()

    def _update_notice(self, rec: Recording, st: str):
        n = self.notice
        self.notice_progress.hide()
        self._notice_fn = {"a": None, "b": None}
        for b in (self.notice_a, self.notice_b):
            b.hide()
        if st in (T_RUNNING, T_QUEUED):
            p = rec.progress() or {}
            if st == T_RUNNING and p.get("total") and p.get("stage") == "transcribing":
                frac = p.get("done", 0) / p["total"]
                self.notice_text.setText(f"Transcribing again… {frac:.0%}  {fmt_eta(p.get('eta_s'))}")
                self.notice_progress.setRange(0, 1000)
                self.notice_progress.setValue(int(frac * 1000))
            else:
                self.notice_text.setText("Transcribing again…" if st == T_RUNNING else "Waiting to transcribe again…")
                self.notice_progress.setRange(0, 0)
            self.notice_progress.show()
            self.notice_a.setText("Cancel")
            self._notice_fn["a"] = self.cancel
            self.notice_a.show()
            n.show()
            return
        if st == T_FAILED:
            self.notice_text.setText(f"Transcribing again failed: {rec.error_text()}")
            self.notice_a.setText("Try again")
            self._notice_fn["a"] = lambda: self.request(None)
            self.notice_a.show()
            n.show()
            return
        if rec.is_edited() and self._newer_model(rec):
            self.notice_text.setText("A newer model transcript is available. Your edits are kept until you switch.")
            self.notice_a.setText("Use new transcript")
            self._notice_fn["a"] = lambda: self.revert(confirm=False)
            self.notice_b.setText("Keep my edits")
            self._notice_fn["b"] = self._keep_edits
            self.notice_a.show()
            self.notice_b.show()
            n.show()
            return
        n.hide()

    @staticmethod
    def _newer_model(rec: Recording) -> bool:
        try:
            return os.stat(rec.path(TRANSCRIPT)).st_mtime > os.stat(rec.path(EDITED)).st_mtime
        except FileNotFoundError:
            return False

    def _keep_edits(self):
        if self.rec:
            os.utime(self.rec.path(EDITED))
            self.refresh()

    # ---- editing ----
    def _on_text_changed(self):
        if self._loading or (self.rec is None and self.linked is None):
            return
        self._corrections = []  # corrections belong to the unedited text
        self._apply_selections()
        self._autosave.start()
        self._realign.start()

    def _align_now(self):
        """Passage spans of the editor's current text, aligned to the model's passages, and the
        flagged passages whose text is still what the model wrote (editing one clears its mark)."""
        if self.linked is not None:
            self._align_set()
            return
        segs = self._segments
        text = self.editor.toPlainText()
        language = ((self.rec.transcript() if self.rec else None) or {}).get("language", "es")
        passages = [(a, b, k) for a, b, k in align.align(segs, text, language) if b > a] if segs else []
        self._passages = passages
        self._spans = [(a, b, float(segs[k].get("start", 0.0))) for a, b, k in passages]
        self._flagged = [(a, b, segs[k]) for a, b, k in passages
                         if segs[k].get("flags") and text[a:b].strip() == (segs[k].get("text") or "").strip()]
        self._update_margin()
        self._apply_selections()
        if self.rec is not None:
            self._update_flag_count()

    def _update_flag_count(self):
        n = len(self._flagged)
        base = self.status.text().split(" · ⚑")[0]
        self.status.setText(base + (f" · ⚑ {n} passage{'s' if n != 1 else ''} to check" if n else ""))

    def _flag_at(self, pos: int):
        return next((seg for a, b, seg in self._flagged if a <= pos <= b), None)

    def _tooltip(self, pos: int) -> str | None:
        seg = self._flag_at(pos)
        if seg is None:
            return "Corrected by the dictionary. Right-click to undo." if self._correction_at(pos) else None
        return "Check this passage: " + "; ".join(flag_reason(f, seg) for f in seg.get("flags", [])) + "."

    def next_flagged(self) -> float | None:
        """Move to the next passage to check after the cursor (wrapping); returns its start time."""
        if not self._flagged:
            return None
        cur = self.editor.textCursor().position()
        a, _b, seg = next(((a, b, sg) for a, b, sg in self._flagged if a > cur), self._flagged[0])
        c = self.editor.textCursor()
        c.setPosition(a)
        self.editor.setTextCursor(c)
        self.editor.ensureCursorVisible()
        return float(seg.get("start", 0.0))

    def _update_margin(self):
        stamps = [(a, t) for a, _b, t in self._spans] if self.show_timestamps else None
        self.editor.set_stamps(stamps, self._marker_anchors(), self._speaker_labels())

    SPEAKER_COLORS = ("accent_deep", "coral_deep", "amber", "accent", "muted")

    def _speaker_labels(self) -> list[tuple[int, str, str, int]]:
        """A name where the speaker changes: the user's, a suggestion with "?", or "Speaker N"."""
        if self.linked is not None:
            return self._set_speaker_labels()
        rec = self.rec
        if rec is None or rec.meta.speakers_off:
            return []
        info = (rec.transcript() or {}).get("speakers") or {}
        if not info:
            return []
        suggested = info.get("suggested") or {}
        out, last = [], None
        for a, _b, k in self._passages:
            n = self._segments[k].get("speaker")
            if n is None or n == last:
                continue
            last = n
            name = rec.meta.speakers.get(str(n)) or (f"{suggested[str(n)]}?" if str(n) in suggested else f"Speaker {n}")
            out.append((a, name, self.SPEAKER_COLORS[(n - 1) % len(self.SPEAKER_COLORS)], n))
        return out

    def _set_speaker_labels(self) -> list[tuple[int, str, str, int]]:
        """Speaker names across a set's parts (naming them is done on the part); a part starts afresh."""
        out, last = [], None
        for a, _b, k in self._passages:
            sg = self._segments[k]
            rec = self._parts[sg["_part"]].rec
            info = (rec.transcript() or {}).get("speakers") or {}
            n = sg.get("speaker")
            key = (sg["_part"], n)
            if rec.meta.speakers_off or not info or n is None or key == last:
                continue
            last = key
            suggested = info.get("suggested") or {}
            name = rec.meta.speakers.get(str(n)) or (f"{suggested[str(n)]}?" if str(n) in suggested else f"Speaker {n}")
            out.append((a, name, self.SPEAKER_COLORS[(n - 1) % len(self.SPEAKER_COLORS)], n))
        return out

    def _speaker_menu(self, n: int, pos):
        if self.linked is not None:
            self.message.emit("Name speakers on the part: click its heading.")
            return
        rec = self.rec
        if rec is None:
            return
        info = (rec.transcript() or {}).get("speakers") or {}
        suggested = (info.get("suggested") or {}).get(str(n))
        current = rec.meta.speakers.get(str(n))
        m = QMenu(self)
        if suggested and not current:
            m.addAction(icon("ok"), f"Yes, this is {suggested}", lambda: self.name_speaker(n, suggested))
        m.addAction(icon("rename"), f"Name speaker {n}…" if not current else f"Rename {current}…",
                    lambda: self._ask_speaker_name(n))
        if current:
            m.addAction(icon("clear"), "Forget this name", lambda: self.name_speaker(n, ""))
        m.addSeparator()
        m.addAction(icon("users"), "No speaker labels for this recording", lambda: self.set_speakers_off(True))
        m.exec(pos)

    def _ask_speaker_name(self, n: int):
        from PySide6.QtWidgets import QInputDialog

        people = [e.name for e in dictionary.current().entries if e.kind == dictionary.PEOPLE]
        current = self.rec.meta.speakers.get(str(n), "") if self.rec else ""
        name, ok = QInputDialog.getItem(self, "Name the speaker", f"Who is speaker {n}?",
                                        ([current] if current else []) + [p for p in people if p != current],
                                        0, True)
        if ok:
            self.name_speaker(n, name.strip())

    def name_speaker(self, n: int, name: str):
        """Name a speaker for the whole recording. A name also becomes a person in the dictionary,
        whose voice is remembered so later recordings suggest it."""
        rec = self.rec
        if rec is None:
            return
        names = dict(rec.meta.speakers)
        if name:
            names[str(n)] = name
            if dictionary.current().find(name) is None and \
                    not self._dict_update(lambda d: d.add(dictionary.PEOPLE, name)):
                return
            centroid = (((rec.transcript() or {}).get("speakers") or {}).get("centroids") or {}).get(str(n))
            if centroid:
                dictionary.remember_voice(dictionary.current().find(name).name, centroid)
        else:
            names.pop(str(n), None)
        rec.update(speakers=names)
        self._update_margin()
        self.changed.emit(rec.id)

    def set_speakers_off(self, off: bool):
        rec = self.rec
        if rec is None or rec.meta.speakers_off == off:
            return
        rec.update(speakers_off=off)
        self.act_speakers.setChecked(not off)
        self._update_margin()
        self.changed.emit(rec.id)
        if not off and not (rec.transcript() or {}).get("speakers"):
            self.message.emit("Transcribe again to label the speakers of this recording.")

    def _marker_anchors(self) -> list[tuple[int, dict]]:
        """Each marker at the start of the passage it falls in (or the next one)."""
        if self.linked is not None:
            markers = [{"at": p.tl.to_set(float(m["at"])), "note": m.get("note") or ""}
                       for p in self._parts for m in p.rec.meta.markers]
        else:
            markers = self.rec.meta.markers if self.rec is not None else []
        if not markers or not self._spans:
            return []
        out = []
        for m in markers:
            at = float(m["at"])
            pos = self._spans[0][0]
            for a, _b, start in self._spans:
                if start <= at + 0.05:
                    pos = a
                else:
                    break
            out.append((pos, m))
        return out

    def reload_markers(self):
        if self.linked is not None:
            for part in self._parts:
                part.rec = self.library.get(part.rec.id) or part.rec
            self._update_margin()
        elif self.rec is not None:
            self.rec = self.library.get(self.rec.id) or self.rec
            self._update_margin()

    def set_show_timestamps(self, on: bool):
        self.show_timestamps = on
        self.times_btn.setChecked(on)
        cfg, _ = settings.load()
        if cfg.show_timestamps != on:
            cfg.show_timestamps = on
            settings.save(cfg)
        self._update_margin()
        self.timestamps_toggled.emit(on)

    def save(self):
        self._autosave.stop()
        if self.linked is not None:
            if self._parts:
                self._save_set()
            return
        rec = self.rec
        if rec is None or self.stack.currentWidget() is not self.page:
            return
        text = self.editor.toPlainText()
        try:
            if text == rec.base_text():
                if rec.is_edited():
                    rec.revert_edits()
            elif text != rec.text() or not rec.is_edited():
                rec.save_edited(text)
            else:
                return
        except OSError as e:
            self.message.emit(f"Could not save your edits: {e}")
            return
        self._shown_signature = self._signature(rec)
        self._update_status(rec)
        self.changed.emit(rec.id)
        if rec.is_edited():
            self._learn_from(rec, text)

    def _learn_from(self, rec: Recording, text: str):
        """After saving edited text: new spellings of known names, and words to offer."""
        d = dictionary.current()
        learned = dictionary.new_aliases(rec.model_text(), text, d)
        if learned:
            # A known name corrected from a new spelling: record it, visibly, without asking.
            if self._dict_update(lambda d: [d.add(d.find(n).kind, n, [a]) for n, a in learned if d.find(n)]):
                self.message.emit(" ".join(f"“{a}” will be corrected to “{n}” from now on." for n, a in learned))
        self._offer(dictionary.edit_candidates(rec.model_text(), text, dictionary.current(), rec.id))

    def revert(self, confirm: bool = True):
        rec = self.rec
        if rec is None:
            return
        if confirm:
            r = QMessageBox.question(self, "Revert to model output",
                                     "Replace your edited text with the model transcript?\n"
                                     "You can undo this with Ctrl+Z until you select another recording.")
            if r != QMessageBox.StandardButton.Yes:
                return
        model_text = rec.base_text()
        cur = self.editor.textCursor()
        cur.beginEditBlock()
        cur.select(QTextCursor.SelectionType.Document)
        cur.insertText(model_text)
        cur.endEditBlock()
        self._autosave.stop()
        rec.revert_edits()
        dictionary.apply(rec, dictionary.current())
        self._load_spans(rec)
        self._apply_selections()
        self._shown_signature = self._signature(rec)
        self._update_status(rec)
        self._update_notice(rec, rec.transcript_status())
        self.changed.emit(rec.id)

    # ---- editing with the audio ----
    def attach_player(self, player):
        self.player = player
        player.span_finished.connect(self._span_done)

    def _passage_at(self, pos: int) -> int | None:
        """Index into _passages of the passage at a text position (or the one before it)."""
        idx = None
        for n, (a, _b, _k) in enumerate(self._passages):
            if a <= pos:
                idx = n
            else:
                break
        return idx if idx is not None else (0 if self._passages else None)

    def _play_passage_n(self, n: int):
        a, _b, k = self._passages[n]
        seg = self._segments[k]
        c = self.editor.textCursor()
        if not (a <= c.position() <= self._passages[n][1]):
            c.setPosition(a)
            self.editor.setTextCursor(c)
            self.editor.ensureCursorVisible()
        self._audio_k = n
        self._typing_paused = False
        self.player.play_span(float(seg.get("start", 0.0)), float(seg.get("end", 0.0)))

    def play_passage(self):
        """Ctrl+.: play the passage under the cursor; again while it plays stops it."""
        if self.player is None or not self._passages:
            return
        n = self._passage_at(self.editor.textCursor().position())
        if self._audio_k == n and (self.player.is_playing() or self._typing_paused):
            self.stop_passage()
            return
        self._play_passage_n(n)

    def step_passage(self, direction: int):
        """Move to the next (1) or previous (-1) passage and play it."""
        if self.player is None or not self._passages:
            return
        n = self._passage_at(self.editor.textCursor().position())
        n = max(0, min(len(self._passages) - 1, n + direction))
        c = self.editor.textCursor()
        c.setPosition(self._passages[n][0])
        self.editor.setTextCursor(c)
        self._play_passage_n(n)

    def play_next_flagged(self):
        if self.player is None:
            return
        if self.next_flagged() is None:
            self.message.emit("No passages to check in this transcript.")
            return
        self._play_passage_n(self._passage_at(self.editor.textCursor().position()))

    def stop_passage(self):
        self._replay.stop()
        self._audio_k = None
        self._typing_paused = False
        if self.player is not None:
            self.player.stop_span()

    def _typing(self):
        """A key in the editor while a passage plays: pause, and replay it once typing stops."""
        if self._audio_k is None or self.player is None or not settings.load()[0].edit_autopause:
            return
        if self.player.is_playing():
            self.player.stop_span()
            self._typing_paused = True
        if self._typing_paused:
            self._replay.start()

    def _replay_passage(self):
        if self._typing_paused and self._audio_k is not None and self._audio_k < len(self._passages):
            self._play_passage_n(self._audio_k)

    def _span_done(self):
        if not self._typing_paused:
            self._audio_k = None

    # ---- dictionary ----
    def _apply_dictionary(self, rec: Recording):
        """Re-run the corrector when the dictionary changed since this transcript was corrected."""
        d = dictionary.current()
        if rec.is_edited() or not rec.path(TRANSCRIPT).exists():
            return
        try:
            dictionary.apply(rec, d)
        except OSError as e:
            log.warning("dictionary correction failed for %s: %s", rec.id, e)

    def _offer(self, candidates):
        d = dictionary.current()
        cand = next((c for c in candidates if not d.knows(c.name)), None)
        self._candidate = cand
        if cand is None:
            self.chip.hide()
            return
        what = "person" if cand.kind == dictionary.PEOPLE else "term"
        alias = f" (instead of “{cand.alias}”)" if cand.alias and cand.alias != cand.name else ""
        self.chip_text.setText(f"Add <b>{_html(cand.name)}</b>{_html(alias)} to the dictionary as a {what}?")
        self.chip.show()

    def offer_title(self, rid: str, title: str):
        """Capitalized words typed into a title are candidates too."""
        rec = self.rec
        if rec is None or rec.id != rid:
            return
        first = rec.text().split(".", 1)[0]
        self._offer(dictionary.title_candidates(title, first, dictionary.current()))

    def _accept_candidate(self):
        cand = self._candidate
        if cand is None:
            return
        if not self._dict_update(lambda d: d.add(cand.kind, cand.name, [cand.alias] if cand.alias else [])):
            return
        self.message.emit(f"Added “{cand.name}” to the dictionary.")
        self._offer([])
        if self.rec is not None:
            self.changed.emit(self.rec.id)

    def _decline_candidate(self):
        cand = self._candidate
        if cand is None:
            return
        if self._dict_update(lambda d: d.mute(cand.name)):
            self._offer([])

    def _dict_update(self, change) -> bool:
        try:
            dictionary.update(change)
            return True
        except dictionary.Unreadable as e:
            self.message.emit(str(e))
            return False

    def _correction_at(self, pos: int):
        return next((e for a, b, e in self._corrections if a <= pos <= b), None)

    def _menu_hook(self, menu, pos: int):
        edit = self._correction_at(pos)
        if edit is None or (self.rec is None and self.linked is None):
            return
        first = menu.actions()[0] if menu.actions() else None
        act = QAction(icon("revert"), f"Undo this correction (back to “{edit['before']}”)", menu)
        act.triggered.connect(lambda: self._undo_correction(edit))
        menu.insertAction(first, act)
        if first is not None:
            menu.insertSeparator(first)

    def _undo_correction(self, edit: dict):
        rec = self.rec if self.linked is None else getattr(self, "_correction_part", {}).get(id(edit))
        if rec is None:
            return
        dictionary.undo(rec, edit)
        self._shown_signature = None
        self.refresh()
        self.changed.emit(rec.id)

    def _fill_languages(self):
        """The languages the model can transcribe; choosing one transcribes the recording in it."""
        m = self.lang_menu
        m.clear()
        rec = self.rec
        if rec is None:
            return
        cfg, _ = settings.load()
        default = cfg.language or models.DEFAULT_LANGUAGE
        a = m.addAction(f"Default ({models.language_name(default)})", lambda: self.set_language(None))
        a.setCheckable(True)
        a.setChecked(rec.meta.language is None)
        m.addSeparator()
        for code in models.supported_languages():
            a = m.addAction(models.language_name(code), lambda c=code: self.set_language(c))
            a.setCheckable(True)
            a.setChecked(rec.meta.language == code)

    def set_language(self, code: str | None):
        rec = self.rec
        if rec is None or rec.meta.language == code:
            return
        before = transcription.language_of(rec)
        rec.update(language=code)
        after = transcription.language_of(rec)
        name = models.language_name(after)
        if after != before and rec.transcript() and features.transcription_installed():
            self.request(None)
            self.message.emit(f"Transcribing again in {name}.")
        else:
            self.message.emit(f"This recording will be transcribed in {name}.")
        self.changed.emit(rec.id)

    # ---- actions ----
    def request(self, adapter: bool | None):
        rec = self.rec
        if rec is None:
            return
        if not features.transcription_installed():
            self.message.emit("Transcription is not installed. Run ./install.sh --with-transcription")
            return
        if not models.all_cached():
            self.download_requested.emit()
            return
        self.save()
        transcription.request(self.library, rec, adapter=adapter)
        self.message.emit("Transcription queued.")
        self.changed.emit(rec.id)
        self.refresh()

    def cancel(self):
        if self.rec is not None:
            transcription.cancel(self.rec)
            self.message.emit("Transcription cancelled.")
            self.changed.emit(self.rec.id)
            self.refresh()

    def _retry_finalize(self):
        rec = self.rec
        if rec is None:
            return

        def go():
            return recorder.finalize(rec)

        def done(outcome):
            self.message.emit({"ready": "Recording saved.", "empty": "The recording had no audio and was removed.",
                               "failed": "Saving failed again; the raw audio is still kept."}[outcome])
            self.changed.emit(rec.id)
            self.refresh()

        run_task(go, on_done=done, on_error=lambda m: self.message.emit(f"Saving failed: {m}"))
        self.state.show_state("Saving…", busy=True)

    def _set_recordings(self) -> list[Recording]:
        return [self.library.get(p.rec.id) or p.rec for p in self._parts]

    def copy_all(self):
        if self.linked is not None:
            self.save()
            QApplication.clipboard().setText(export.render_set(self.linked.title, self._set_recordings(), ".txt"))
            self.message.emit("All parts copied.")
            return
        if self.rec is None or self.stack.currentWidget() is not self.page:
            return
        self.save()
        QApplication.clipboard().setText(self.editor.toPlainText().strip() + "\n")
        self.message.emit("Transcript copied.")

    def export_text(self):
        rec = self.rec
        if (rec is None and self.linked is None) or self.stack.currentWidget() is not self.page:
            return
        self.save()
        if self.linked is not None:
            from types import SimpleNamespace

            name = export.suggested_name(SimpleNamespace(meta=SimpleNamespace(title=self.linked.title), id=self.linked.id),
                                         ".txt")
        else:
            name = export.suggested_name(rec, ".txt")
        start = os.path.join(os.path.expanduser("~"), name)
        filters = [f"{label} (*{ext})" for ext, label in export.TEXT_FORMATS.items()]
        path, flt = QFileDialog.getSaveFileName(self, "Export transcript", start, ";;".join(filters))
        if not path:
            return
        ext = flt[flt.rfind("*") + 1:flt.rfind(")")] if "*" in flt else ".txt"
        if not path.lower().endswith(tuple(export.TEXT_FORMATS)):
            path += ext
        try:
            if self.linked is not None:
                out = export.export_set(self.linked.title, self._set_recordings(), path, self.linked.id)
            else:
                out = export.export_transcript(rec, path)
        except OSError as e:
            self.message.emit(f"Export failed: {e}")
            return
        self.message.emit(f"Saved {out}")

    def copy_with_timestamps(self):
        if self.linked is not None:
            self.save()
            QApplication.clipboard().setText(export.set_with_timestamps(self._set_recordings()))
            self.message.emit("All parts copied with passage times.")
            return
        if self.rec is None or self.stack.currentWidget() is not self.page:
            return
        self.save()
        QApplication.clipboard().setText(export.with_timestamps(self.rec))
        self.message.emit("Transcript copied with passage times.")

    def has_text(self) -> bool:
        return self.stack.currentWidget() is self.page

    # ---- find ----
    def open_find(self):
        if self.stack.currentWidget() is not self.page:
            return
        self.findbar.show()
        self._find_from_search = False
        sel = self.editor.textCursor().selectedText()
        if sel and " " not in sel:
            self.find_edit.setText(sel)
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        self._find_update()

    def find_from_search(self, text: str):
        """Show the find bar with the library search's words, leaving the focus where it is
        (the list, while the user steps through results)."""
        if self.stack.currentWidget() is not self.page:
            return
        self.findbar.show()
        self._find_from_search = True
        cur = self.editor.textCursor()
        cur.setPosition(0)  # from the first occurrence, as a newly opened result
        self.editor.setTextCursor(cur)
        if self.find_edit.text() == text:
            self._find_update()
        else:
            self.find_edit.setText(text)  # runs _find_update

    def search_cleared(self):
        """The library search was cleared: its find bar goes too, one the user opened stays."""
        if self._find_from_search and self.findbar.isVisible():
            self.close_find(focus=False)

    def close_find(self, focus: bool = True):
        self._find_from_search = False
        self.findbar.hide()
        self._find_matches = []
        self._apply_selections()
        if focus and self.stack.currentWidget() is self.page:
            self.editor.setFocus()

    def _find_update(self):
        q = _fold(self.find_edit.text())
        self._find_matches = []
        if q:
            hay = _fold(self.editor.toPlainText())
            self._find_matches = _occurrences(hay, q)
            if not self._find_matches and len(q.split()) > 1:
                # The library search matches the words anywhere, so a search carried over from it
                # (or typed here) that is not a phrase in this text finds each word instead.
                spans = sorted(m for w in set(q.split()) for m in _occurrences(hay, w))
                for a, b in spans:
                    if not self._find_matches or a >= self._find_matches[-1][1]:
                        self._find_matches.append((a, b))
        self._find_index = -1
        self._find_step(1)

    def _find_step(self, direction: int):
        n = len(self._find_matches)
        if not n:
            self.find_count.setText("No matches" if self.find_edit.text() else "")
            self._apply_selections()
            return
        pos = self.editor.textCursor().selectionStart() if self._find_index < 0 else None
        if pos is not None and direction > 0:
            self._find_index = next((k for k, (a, _) in enumerate(self._find_matches) if a >= pos), 0)
        else:
            self._find_index = (self._find_index + direction) % n
        a, b = self._find_matches[self._find_index]
        cur = self.editor.textCursor()
        cur.setPosition(a)
        cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cur)
        self.editor.ensureCursorVisible()
        self.find_count.setText(f"{self._find_index + 1} of {n}")
        self._apply_selections()

    # ---- follow-along ----
    def follow(self, sec: float):
        if not self._spans or self.stack.currentWidget() is not self.page:
            return
        idx = -1
        for k, (_a, _b, start) in enumerate(self._spans):
            if start <= sec + 0.05:
                idx = k
            else:
                break
        if idx != self._current_span:
            self._current_span = idx
            self._apply_selections()
            if idx >= 0 and not self.editor.hasFocus():
                cur = QTextCursor(self.editor.document())
                cur.setPosition(self._spans[idx][0])
                self.editor.setTextCursor(cur)
                self.editor.ensureCursorVisible()

    def _on_ctrl_click(self, pos: int):
        for a, b, start in self._spans:
            if a <= pos <= b:
                self.seek_requested.emit(start)
                return

    def _apply_selections(self):
        sels = []
        doc_end = self.editor.document().characterCount() - 1
        for a, b, _seg in getattr(self, "_flagged", []):
            s = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(theme.color("amber", 0.16 if not theme.current().dark else 0.22))
            s.format = fmt
            cur = QTextCursor(self.editor.document())
            cur.setPosition(min(a, doc_end))
            cur.setPosition(min(b, doc_end), QTextCursor.MoveMode.KeepAnchor)
            s.cursor = cur
            sels.append(s)
        for a, b, _e in self._corrections:
            s = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DashUnderline)
            fmt.setUnderlineColor(QColor(theme.current().accent))
            s.format = fmt
            cur = QTextCursor(self.editor.document())
            cur.setPosition(min(a, doc_end))
            cur.setPosition(min(b, doc_end), QTextCursor.MoveMode.KeepAnchor)
            s.cursor = cur
            sels.append(s)
        if 0 <= self._current_span < len(self._spans):
            a, b, _ = self._spans[self._current_span]
            s = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(theme.current().accent_soft))
            s.format = fmt
            cur = QTextCursor(self.editor.document())
            cur.setPosition(a)
            cur.setPosition(min(b, self.editor.document().characterCount() - 1), QTextCursor.MoveMode.KeepAnchor)
            s.cursor = cur
            sels.append(s)
        if self.findbar.isVisible():
            for k, (a, b) in enumerate(self._find_matches):
                s = QTextEdit.ExtraSelection()
                fmt = QTextCharFormat()
                fmt.setBackground(QColor(theme.current().amber) if k == self._find_index
                                  else theme.color("find", 0.45))
                if k == self._find_index:
                    fmt.setForeground(QColor(theme.LAGOON_LIGHT.ink))
                s.format = fmt
                cur = QTextCursor(self.editor.document())
                cur.setPosition(a)
                cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                s.cursor = cur
                sels.append(s)
        self.editor.setExtraSelections(sels)

    def sizeHint(self) -> QSize:
        return QSize(500, 400)

