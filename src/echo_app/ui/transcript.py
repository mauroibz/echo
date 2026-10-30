"""Transcript panel: the shown recording or set, autosaving edits, actions and follow-along.

The editor widget is in `editor`, sets, speakers and find in the `transcript_*` mixins."""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget,
                               QTextEdit, QToolButton, QVBoxLayout, QWidget)

from .. import align, dictionary, export, features, models, recorder, settings, transcription
from ..library import (CORRECTED, EDITED, RELABELED, NEEDS_FINALIZE, READY, RECORDING, T_FAILED, T_QUEUED, T_RUNNING,
                       TRANSCRIPT, Library, Recording)
from . import motion, theme
from .common import fmt_date, fmt_duration, fmt_eta, icon, run_task
from .editor import Editor, StateView
from .transcript_find import FindMixin
from .transcript_sets import SetPart, SetsMixin
from .transcript_speakers import SpeakersMixin
from .transcript_text import (AUTOSAVE_MS, BASE_MARGIN, REPLAY_AFTER_MS, _estimate, _html, _plain,
                              flag_reason, segment_offsets, shown_segments)

log = logging.getLogger(__name__)


class TranscriptPanel(SetsMixin, SpeakersMixin, FindMixin, QWidget):
    """The transcript of the selected recording or set: state, editor, saving and the actions on
    it. Linked sets, speakers and finding live in their mixins (transcript_sets, _speakers, _find)."""

    seek_requested = Signal(float)
    part_requested = Signal(str)  # a linked set's part heading was clicked: show that recording
    message = Signal(str)
    download_requested = Signal()
    changed = Signal(str)  # recording id whose files changed
    timestamps_toggled = Signal(bool)
    marker_clicked = Signal(float)
    profile_requested = Signal(str)  # a person's name: open their profile

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
        self._find_speakers: set[int] | None = None  # a speaker search: find only in their passages
        self._shown_signature = None
        self._autosave = QTimer(self, singleShot=True, interval=AUTOSAVE_MS, timeout=self.save)
        # While typing, passage positions follow the text a moment later (alignment of the edit).
        self._realign = QTimer(self, singleShot=True, interval=400, timeout=self._align_now)
        self._segments: list[dict] = []
        self._flagged: list[tuple[int, int, dict]] = []
        self._passages: list[tuple[int, int, int]] = []  # (start, end, segment index) in the shown text
        self._pieces: list[tuple[int, int, int, int | None]] = []  # (start, end, segment, speaker) after fixes
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
        # The window shows these elsewhere (the status in Details, the buttons in the header), so
        # the bar itself stays hidden; a window that wants it back shows `toolbar`.
        self.toolbar = QWidget()
        bar = QHBoxLayout(self.toolbar)
        bar.setContentsMargins(0, 0, 0, 0)
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
        self.more_menu = menu
        bar.addWidget(self.more_btn)
        pl.addWidget(self.toolbar)

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
        self.editor.document().setDocumentMargin(BASE_MARGIN)
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

        # Naming speakers: one unnamed speaker at a time, most speech first, after the chip above
        # is answered.
        # Nothing here takes the keyboard focus unless the user clicks into the name field.
        self.namebar = QFrame()
        self.namebar.setObjectName("chip")
        nl = QHBoxLayout(self.namebar)
        nl.setContentsMargins(6, 4, 6, 4)
        nl.setSpacing(6)
        self.name_play = QToolButton()
        self.name_play.setIcon(icon("play"))
        self.name_play.setToolTip("Hear this speaker")
        self.name_play.setAccessibleName("Hear this speaker")
        self.name_play.clicked.connect(self._play_speaker)
        nl.addWidget(self.name_play)
        self.name_text = QLabel()
        self.name_text.setTextFormat(Qt.TextFormat.RichText)
        nl.addWidget(self.name_text, 1)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name")
        self.name_edit.setAccessibleName("Speaker name")
        self.name_edit.setMinimumWidth(160)
        self.name_edit.returnPressed.connect(self._name_typed)
        nl.addWidget(self.name_edit)
        self.name_yes = QPushButton(icon("ok"), "")
        self.name_yes.clicked.connect(self._name_suggested)
        nl.addWidget(self.name_yes)
        self.name_other = QPushButton("Someone else…")
        self.name_other.clicked.connect(self._name_someone_else)
        nl.addWidget(self.name_other)
        self.name_me = QPushButton("It's me")
        self.name_me.setToolTip("Echo learns your voice and names you in later recordings by itself")
        self.name_me.clicked.connect(self._name_me)
        nl.addWidget(self.name_me)
        self.name_skip = QPushButton("Not now")
        self.name_skip.setToolTip("Do not ask about this recording's speakers again (the margin still names them)")
        self.name_skip.clicked.connect(self._name_dismiss)
        nl.addWidget(self.name_skip)
        for b in (self.name_play, self.name_yes, self.name_other, self.name_me, self.name_skip):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._ask: int | None = None  # the speaker the bar asks about
        self._ask_typing = False  # "Someone else…" was pressed: the name field replaces the suggestion
        self._ask_your_name = False  # "It's me" before Echo knows the user's name
        self.namebar.hide()
        pl.insertWidget(pl.indexOf(column), self.namebar)  # at the top, over the text it names

        self.findbar = QWidget()
        fl = QHBoxLayout(self.findbar)
        fl.setContentsMargins(0, 0, 0, 0)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find in transcript")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.textChanged.connect(self._find_update)
        self.find_edit.textEdited.connect(self._find_typed)
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
        return (rec.id, mt(TRANSCRIPT), rec.is_edited(), mt(CORRECTED), mt(RELABELED))

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
        self._update_namebar()  # names may have changed without the text: elsewhere, or by the worker

    def _load_text(self, rec: Recording):
        self._loading = True
        text = rec.text()
        if self.editor.toPlainText() != _plain(text):
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
            n = len(rec.speaker_numbers())
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
        fixes = self.rec.fixes() if self.rec is not None else []
        self._pieces = align.speaker_pieces(segs, text, passages, fixes) if segs else []
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
        self._update_namebar()

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
            if text == _plain(rec.base_text()):
                if rec.is_edited():
                    rec.revert_edits()
            elif text != _plain(rec.text()) or not rec.is_edited():
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
            self._update_namebar()
            return
        what = "person" if cand.kind == dictionary.PEOPLE else "term"
        alias = f" (instead of “{cand.alias}”)" if cand.alias and cand.alias != cand.name else ""
        self.chip_text.setText(f"Add <b>{_html(cand.name)}</b>{_html(alias)} to the dictionary as a {what}?")
        self.chip.show()
        self._update_namebar()

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
        self._speaker_menu_items(menu, pos)
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
                self._scroll_to_cursor()

    def _scroll_to_cursor(self):
        """Bring the passage that plays into view: smoothly, and only when it is out of view."""
        ed = self.editor
        r = ed.cursorRect()
        h = ed.viewport().height()
        if 0 <= r.top() and r.bottom() <= h:
            return
        if not motion.on():
            ed.ensureCursorVisible()
            return
        bar = ed.verticalScrollBar()
        # QPlainTextEdit scrolls by lines: find the line that puts the passage a third of the way down.
        lines = max(1, round((r.top() - h / 3) / max(1, ed.fontMetrics().lineSpacing())))
        target = max(bar.minimum(), min(bar.maximum(), bar.value() + lines))
        anim = QPropertyAnimation(bar, b"value", self)
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.setDuration(motion.MEDIUM)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

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

