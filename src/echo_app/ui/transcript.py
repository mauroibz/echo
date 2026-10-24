"""Transcript panel: state views, the autosaving editor, find, follow-along."""

from __future__ import annotations

import logging
import os
import unicodedata

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QKeySequence, QMouseEvent, QPalette, QTextCharFormat, QTextCursor,
                           QTextFormat)
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QTextEdit, QToolButton,
                               QVBoxLayout, QWidget)

from .. import export, features, models, recorder, transcription
from ..library import (EDITED, NEEDS_FINALIZE, READY, RECORDING, T_DONE, T_FAILED, T_NONE, T_QUEUED, T_RUNNING,
                       TRANSCRIPT, Library, Recording)
from .common import fmt_date, fmt_duration, fmt_eta, icon, run_task

log = logging.getLogger(__name__)

AUTOSAVE_MS = 1000


def _fold(text: str) -> str:
    """Lower-case, accent-free copy with the same length (for accent-insensitive find)."""
    return "".join((unicodedata.normalize("NFD", c)[0] if c else c).lower() for c in text)


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


class Editor(QPlainTextEdit):
    ctrl_clicked = Signal(int)  # character position
    MAX_TEXT_WIDTH_CHARS = 90

    def mousePressEvent(self, e: QMouseEvent):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier and e.button() == Qt.MouseButton.LeftButton:
            self.ctrl_clicked.emit(self.cursorForPosition(e.position().toPoint()).position())
            return
        super().mousePressEvent(e)


class StateView(QWidget):
    """Centered message with optional progress bar and buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self.headline = QLabel()
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 1.2)
        f.setWeight(QFont.Weight.DemiBold)
        self.headline.setFont(f)
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.headline.setWordWrap(True)
        lay.addWidget(self.headline)
        self.detail = QLabel()
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
                   busy: bool = False, actions=()):
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
            self.buttons.addWidget(b)
            self._btns.append(b)
        self.buttons.addStretch(1)


class TranscriptPanel(QWidget):
    seek_requested = Signal(float)
    message = Signal(str)
    download_requested = Signal()
    changed = Signal(str)  # recording id whose files changed

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.library = library
        self.rec: Recording | None = None
        self._loading = False
        self._spans: list[tuple[int, int, float]] = []
        self._current_span = -1
        self._find_matches: list[tuple[int, int]] = []
        self._find_index = -1
        self._shown_signature = None
        self._autosave = QTimer(self, singleShot=True, interval=AUTOSAVE_MS, timeout=self.save)
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
        pl.setContentsMargins(12, 6, 12, 8)
        pl.setSpacing(6)
        bar = QHBoxLayout()
        self.status = QLabel()
        dimpal = self.status.palette()
        c = dimpal.color(QPalette.ColorRole.WindowText)
        c.setAlpha(170)
        dimpal.setColor(QPalette.ColorRole.WindowText, c)
        self.status.setPalette(dimpal)
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

        self.copy_btn = tool("Copy", "copy", self.copy_all, "Copy the whole transcript (Ctrl+Shift+C)")
        self.export_btn = tool("Export…", "export", self.export_text, "Save as .txt or .md (Ctrl+E)")
        self.more_btn = QToolButton()
        self.more_btn.setText("More")
        self.more_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.more_btn)
        self.act_find = menu.addAction(icon("find"), "Find…", self.open_find)
        self.act_find.setShortcut(QKeySequence.StandardKey.Find)
        menu.addSeparator()
        self.act_retx = menu.addAction(icon("transcribe"), "Transcribe again", lambda: self.request(None))
        self.act_retx_base = menu.addAction("Transcribe again without the Spanish adapter", lambda: self.request(False))
        self.act_revert = menu.addAction(icon("revert"), "Revert to model output…", self.revert)
        self.more_btn.setMenu(menu)
        bar.addWidget(self.more_btn)
        pl.addLayout(bar)

        self.notice = QFrame()
        self.notice.setFrameShape(QFrame.Shape.StyledPanel)
        nl = QHBoxLayout(self.notice)
        nl.setContentsMargins(8, 4, 8, 4)
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
        self.editor.setFrameShape(QFrame.Shape.NoFrame)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setTabChangesFocus(True)
        self.editor.setAccessibleName("Transcript")
        ef = QFont(self.font())
        ef.setPointSizeF(ef.pointSizeF() * 1.12)
        self.editor.setFont(ef)
        self.editor.document().setDocumentMargin(10)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.ctrl_clicked.connect(self._on_ctrl_click)
        # Centered reading column on wide windows, on a full-width text background.
        column = QWidget()
        column.setAutoFillBackground(True)
        cpal = column.palette()
        cpal.setColor(QPalette.ColorRole.Window, cpal.color(QPalette.ColorRole.Base))
        column.setPalette(cpal)
        cl = QHBoxLayout(column)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addStretch(1)
        self.editor.setMaximumWidth(self.editor.fontMetrics().averageCharWidth() * Editor.MAX_TEXT_WIDTH_CHARS + 60)
        cl.addWidget(self.editor, 100)
        cl.addStretch(1)
        pl.addWidget(column, 1)

        self.findbar = QWidget()
        fl = QHBoxLayout(self.findbar)
        fl.setContentsMargins(0, 0, 0, 0)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find in transcript")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.textChanged.connect(self._find_update)
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
        if self.rec is not None and (rec is None or rec.id != self.rec.id):
            self.save()
        switching = rec is None or self.rec is None or rec.id != self.rec.id
        self.rec = rec
        if switching:
            self._shown_signature = None
            self.close_find()
        self.refresh()

    def _signature(self, rec: Recording):
        def mt(name):
            try:
                return os.stat(rec.path(name)).st_mtime_ns
            except FileNotFoundError:
                return None
        return (rec.id, mt(TRANSCRIPT), rec.is_edited())

    def refresh(self):
        """Re-evaluate what to show for the current recording (called on every library change)."""
        rec = self.rec
        if rec is None:
            self.stack.setCurrentWidget(self.state)
            self.state.show_state("No recording selected", "Select a recording on the left to see its transcript.")
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
                                  else "You can transcribe it after you stop.")
            return
        if rec.meta.state == NEEDS_FINALIZE:
            self.stack.setCurrentWidget(self.state)
            self.state.show_state("This recording needs attention",
                                  (rec.meta.error or "Saving did not complete.") +
                                  "\nThe raw audio is safe on disk.",
                                  actions=[("Try saving again", "ok", self._retry_finalize, True)])
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
            if stage in ("loading", "detecting"):
                head = "Loading the model…" if stage == "loading" else "Finding speech…"
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
            self.state.show_state("Transcription failed", err, actions=actions)
        else:
            if not features.transcription_installed():
                self.state.show_state("Transcription is not installed",
                                      "Install it from the Echo folder with:\n./install.sh --with-transcription")
            elif not models.all_cached():
                self.state.show_state("Not transcribed yet",
                                      "The transcription model needs to be downloaded once (about 4.3 GB).",
                                      actions=[("Download model…", "download", self.download_requested.emit, True)])
            else:
                dur = f" ({fmt_duration(rec.meta.duration)})" if rec.meta.duration else ""
                self.state.show_state("Not transcribed yet", f"Transcribe this recording{dur} on this computer.",
                                      actions=[("Transcribe", "transcribe", lambda: self.request(None), True)])

    def _show_editor(self, rec: Recording, st: str):
        self.stack.setCurrentWidget(self.page)
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
        t = rec.transcript() or {}
        self._spans = segment_spans(t.get("segments", [])) if not rec.is_edited() else []
        self._current_span = -1
        self._apply_selections()

    def _update_status(self, rec: Recording):
        t = rec.transcript() or {}
        when = fmt_date(t.get("created", "")) if t else ""
        model = "Spanish adapter" if (t.get("model") or {}).get("adapter_enabled") else "base model"
        if rec.is_edited():
            self.status.setText("Edited" + (f" · model transcript from {when}" if when else ""))
        elif t:
            self.status.setText(f"Model transcript · {when} · {model}")
        else:
            self.status.setText("")
        self.act_revert.setEnabled(rec.is_edited() and bool(t))
        installed = features.transcription_installed()
        self.act_retx.setEnabled(installed)
        self.act_retx_base.setEnabled(installed)

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
        if self._loading or self.rec is None:
            return
        self._spans = []  # edits break the passage mapping
        self._apply_selections()
        self._autosave.start()

    def save(self):
        self._autosave.stop()
        rec = self.rec
        if rec is None or self.stack.currentWidget() is not self.page:
            return
        text = self.editor.toPlainText()
        try:
            if text == rec.model_text():
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
        model_text = rec.model_text()
        cur = self.editor.textCursor()
        cur.beginEditBlock()
        cur.select(QTextCursor.SelectionType.Document)
        cur.insertText(model_text)
        cur.endEditBlock()
        self._autosave.stop()
        rec.revert_edits()
        t = rec.transcript() or {}
        self._spans = segment_spans(t.get("segments", []))
        self._shown_signature = self._signature(rec)
        self._update_status(rec)
        self._update_notice(rec, rec.transcript_status())
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

    def copy_all(self):
        if self.rec is None or self.stack.currentWidget() is not self.page:
            return
        self.save()
        QApplication.clipboard().setText(self.editor.toPlainText().strip() + "\n")
        self.message.emit("Transcript copied.")

    def export_text(self):
        rec = self.rec
        if rec is None or self.stack.currentWidget() is not self.page:
            return
        self.save()
        start = os.path.join(os.path.expanduser("~"), export.suggested_name(rec, ".txt"))
        path, flt = QFileDialog.getSaveFileName(self, "Export transcript", start, "Text (*.txt);;Markdown (*.md)")
        if not path:
            return
        if flt.startswith("Markdown") and not path.lower().endswith(".md"):
            path += ".md"
        try:
            out = export.export_transcript(rec, path)
        except OSError as e:
            self.message.emit(f"Export failed: {e}")
            return
        self.message.emit(f"Saved {out}")

    def has_text(self) -> bool:
        return self.stack.currentWidget() is self.page

    # ---- find ----
    def open_find(self):
        if self.stack.currentWidget() is not self.page:
            return
        self.findbar.show()
        sel = self.editor.textCursor().selectedText()
        if sel and " " not in sel:
            self.find_edit.setText(sel)
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        self._find_update()

    def close_find(self):
        self.findbar.hide()
        self._find_matches = []
        self._apply_selections()
        if self.stack.currentWidget() is self.page:
            self.editor.setFocus()

    def _find_update(self):
        q = _fold(self.find_edit.text())
        self._find_matches = []
        if q:
            hay = _fold(self.editor.toPlainText())
            i = hay.find(q)
            while i >= 0:
                self._find_matches.append((i, i + len(q)))
                i = hay.find(q, i + 1)
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
        if self.rec is not None and self.rec.is_edited():
            self.message.emit("Ctrl+click to jump works on the unedited model transcript.")

    def _apply_selections(self):
        sels = []
        pal = self.editor.palette()
        if 0 <= self._current_span < len(self._spans):
            a, b, _ = self._spans[self._current_span]
            s = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            hl = QColor(pal.color(QPalette.ColorRole.Highlight))
            hl.setAlpha(45)
            fmt.setBackground(hl)
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
                fmt.setBackground(QColor("#f5a524") if k == self._find_index else QColor(245, 165, 36, 90))
                if k == self._find_index:
                    fmt.setForeground(QColor("#000000"))
                s.format = fmt
                cur = QTextCursor(self.editor.document())
                cur.setPosition(a)
                cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                s.cursor = cur
                sels.append(s)
        self.editor.setExtraSelections(sels)

    def sizeHint(self) -> QSize:
        return QSize(500, 400)


def _unused():
    _ = (QTextFormat, T_DONE, T_NONE)
