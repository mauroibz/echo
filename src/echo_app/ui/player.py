"""Player: the selected recording's header, its playback dock and the pieces Details shows; the
waveform itself is in `waveform`."""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

from ..audio import peaks as peaks_mod
from ..audio.playback import MAX_VOLUME, Playback, SetPlayback
from ..library import READY, Recording
from . import motion, theme
from .common import fmt_date, fmt_duration, fmt_length, icon, run_task
from .waveform import WaveformView

log = logging.getLogger(__name__)


def statistics(rec: Recording) -> str:
    """"1,234 words · 142 words a minute · 18% silence" from the transcript, or ""."""
    t = rec.transcript()
    if not t or not t.get("segments"):
        return ""
    words = len(rec.text().split())
    speech = sum(max(0.0, float(s.get("end", 0)) - float(s.get("start", 0))) for s in t["segments"] if s.get("text"))
    start, end = rec.effective_span()
    span = (end if end is not None else (rec.meta.duration or 0)) - start
    parts = [f"{words:,} words"]
    if speech > 0:
        parts.append(f"{round(words / speech * 60)} words a minute")
    if span > 0 and speech <= span:
        parts.append(f"{round(100 * (1 - speech / span))}% silence")
    return "  ·  ".join(parts)


class PlayerPanel(QWidget):
    renamed = Signal(str, str)  # recording id, new title
    set_renamed = Signal(str, str)  # set id, new title
    markers_changed = Signal(str)  # recording id
    meta_changed = Signal(str)  # recording id whose tags or notes changed
    span_finished = Signal()  # a passage started with play_span reached its end
    crop_saved = Signal(str)
    export_requested = Signal()
    position_changed = Signal(float)
    message = Signal(str)

    SPEEDS = (1.0, 1.25, 1.5, 2.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rec: Recording | None = None
        self.linked = None  # the LinkedSet shown instead of a recording
        self.parts: list = []  # its sets.Part timeline
        self._loaded_sha = None
        self._span: tuple[float, float] | None = None
        self._rec_player = Playback()
        self._set_player = SetPlayback()
        self.player = self._rec_player
        self.volumes: dict[str, float] = {}  # recording or set id -> volume, only those not at 100%
        self._build()
        self._timer = QTimer(self, interval=40, timeout=self._tick)
        self.set_recording(None)

    def _build(self):
        """The parts, in three places the window lays out: `header` (title, one line, tags), `dock`
        (playback along the bottom) and the pieces of Details (`context`, `notes`, `file_info`,
        `stats`). The panel itself is not shown."""
        self.header = QWidget()
        hl = QVBoxLayout(self.header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        self.title = QLineEdit()
        self.title.setFrame(False)
        self.title.setObjectName("title")
        self.title.setFont(theme.display_font(1.9, QFont.Weight.ExtraBold))
        self.title.setPlaceholderText("Untitled")
        self.title.setToolTip("Rename (F2)")
        self.title.setAccessibleName("Title")
        self.title.editingFinished.connect(self._commit_title)
        hl.addWidget(self.title)
        line = QHBoxLayout()
        line.setContentsMargins(5, 0, 0, 0)
        line.setSpacing(12)
        self.subtitle = QLabel("")
        self.subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        theme.set_role(self.subtitle, dim=True)
        line.addWidget(self.subtitle)
        from .tags import NotesEdit, TagEditor

        self.tags = TagEditor()
        self.tags.changed.connect(self._commit_tags)
        line.addWidget(self.tags, 1)
        hl.addLayout(line)

        self.context = QLineEdit()
        self.context.setObjectName("context")
        self.context.setPlaceholderText("Who is speaking, what about (optional)")
        self._context_tip = ("Used as context when this recording is transcribed, together with the dictionary.\n"
                             "For example: Entrevista con Lucía sobre PipeWire")
        self.context.setToolTip(self._context_tip)
        self.context.setAccessibleName("Who is speaking, what about")
        self.context.editingFinished.connect(self._commit_context)
        self.notes = NotesEdit()
        self.notes.edited.connect(self._commit_notes)
        self.file_info = QLabel("")
        self.file_info.setWordWrap(True)
        self.file_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.stats = QLabel("")
        self.stats.setWordWrap(True)

        self.dock = QWidget()
        self.dock.setObjectName("dock")
        row = QHBoxLayout(self.dock)
        row.setContentsMargins(20, 10, 16, 10)
        row.setSpacing(12)
        self.play_btn = QToolButton()
        self.play_btn.setObjectName("play")
        self.play_btn.setIcon(icon("play", "on_accent"))
        self.play_btn.setIconSize(QSize(18, 18))
        self.play_btn.setFixedSize(44, 44)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setToolTip("Play / pause (Space)")
        self.play_btn.setAccessibleName("Play")
        self.play_btn.clicked.connect(self.toggle_play)
        row.addWidget(self.play_btn)
        self.time = QLabel("0:00")
        self.time.setFont(theme.display_font(0.95, QFont.Weight.Bold, tabular=True))
        self.time.setMinimumWidth(self.time.fontMetrics().horizontalAdvance("0:00:00") + 4)
        row.addWidget(self.time)
        self.wave = WaveformView()
        self.wave.setMinimumHeight(44)
        self.wave.setMaximumHeight(52)
        self.wave.seek_requested.connect(self.seek)
        self.wave.crop_changed.connect(self._crop_changed)
        self.wave.markers_edited.connect(self._markers_edited)
        row.addWidget(self.wave, 1)
        self.total = QLabel("0:00")
        self.total.setFont(theme.display_font(0.95, QFont.Weight.DemiBold, tabular=True))
        theme.set_role(self.total, dim=True)
        row.addWidget(self.total)
        self.crop_label = QLabel("")
        theme.set_role(self.crop_label, dim=True)
        row.addWidget(self.crop_label)
        self.clear_crop_btn = QToolButton()
        self.clear_crop_btn.setIcon(icon("clear", "muted"))
        self.clear_crop_btn.setToolTip("Clear the crop")
        self.clear_crop_btn.setAccessibleName("Clear crop")
        self.clear_crop_btn.clicked.connect(self.clear_crop)
        row.addWidget(self.clear_crop_btn)
        # Speed: one button that steps through the speeds (its menu lists them); the combo box
        # holds the value.
        self.speed = QComboBox(self)
        for s in self.SPEEDS:
            self.speed.addItem(f"{s:g}×", s)
        self.speed.hide()
        self.speed.currentIndexChanged.connect(lambda _i: self.player.set_speed(self.speed.currentData()))
        self.speed_btn = QToolButton()
        self.speed_btn.setObjectName("pill")
        self.speed_btn.setFont(theme.display_font(0.9, QFont.Weight.Bold, tabular=True))
        self.speed_btn.setToolTip("Playback speed: click for the next one")
        self.speed_btn.setAccessibleName("Playback speed")
        self.speed_btn.clicked.connect(lambda: self.speed.setCurrentIndex((self.speed.currentIndex() + 1)
                                                                          % self.speed.count()))
        self.speed.currentIndexChanged.connect(lambda _i: self.speed_btn.setText(self.speed.currentText()))
        self.speed_btn.setText(self.speed.currentText())
        row.addWidget(self.speed_btn)
        # Volume, for quiet recordings: up to 400% (a limiter keeps the boost from clipping), in a
        # popup. Each change restarts the pipeline, so a drag applies once the slider settles.
        self.volume_btn = QToolButton()
        self.volume_btn.setIcon(icon("volume", "muted"))
        self.volume_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.volume_btn.setFont(theme.display_font(0.85, QFont.Weight.Bold, tabular=True))
        self.volume_btn.setToolTip("Volume")
        self.volume_btn.setAccessibleName("Volume")
        self.volume_btn.clicked.connect(self._open_volume)
        row.addWidget(self.volume_btn)
        self.volume_popup = QFrame(self, Qt.WindowType.Popup)
        self.volume_popup.setObjectName("popup")
        vl = QHBoxLayout(self.volume_popup)
        vl.setContentsMargins(14, 10, 10, 10)
        vl.setSpacing(8)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, round(MAX_VOLUME * 100))
        self.volume.setSingleStep(5)
        self.volume.setPageStep(10)
        self.volume.setValue(100)
        self.volume.setFixedWidth(180)
        self.volume.setToolTip("Volume. Above 100% boosts quiet recordings; the audio file is not changed.\n"
                               "Remembered for each recording. Double-click for 100%.")
        self.volume.setAccessibleName("Volume")
        self.volume.valueChanged.connect(self._volume_moved)
        self.volume.installEventFilter(self)
        vl.addWidget(self.volume)
        self.volume_label = QToolButton()
        self.volume_label.setText("100%")
        self.volume_label.setFont(theme.display_font(0.85, QFont.Weight.Bold, tabular=True))
        self.volume_label.setMinimumWidth(self.volume_label.fontMetrics().horizontalAdvance("400%") + 12)
        self.volume_label.setToolTip("Back to 100%")
        self.volume_label.setAccessibleName("Reset volume to 100%")
        self.volume_label.clicked.connect(lambda: self.volume.setValue(100))
        vl.addWidget(self.volume_label)
        self._volume_timer = QTimer(self, singleShot=True, interval=150, timeout=self._apply_volume)
        self.export_btn = QToolButton(self)  # exporting is in the header's Export menu
        self.export_btn.hide()
        self.export_btn.clicked.connect(self.export_requested.emit)

    def _open_volume(self):
        self.volume_popup.adjustSize()
        at = self.volume_btn.mapToGlobal(self.volume_btn.rect().topRight())
        self.volume_popup.move(at.x() - self.volume_popup.width(), at.y() - self.volume_popup.height() - 6)
        self.volume_popup.show()
        self.volume.setFocus()

    # ---- recording ----
    def _leave_set(self):
        if self.linked is None:
            return
        self._set_player.stop()
        self._rec_player.set_speed(self._set_player.speed)
        self.player = self._rec_player
        self.linked, self.parts = None, []
        self.wave.editable, self.wave.dividers = True, []
        for w in (self.tags, self.notes):
            w.show()
        self.title.setToolTip("Rename (F2)")
        self.context.setToolTip(self._context_tip)

    def set_linked(self, linked, parts: list[Recording]):
        """Show a linked set: its title, its parts on one timeline, read-only waveform."""
        from .. import sets

        same = self.linked is not None and linked.id == self.linked.id
        timeline = sets.timeline(parts)
        sig = [(p.rec.id, p.rec.meta.sha256, p.start, p.length) for p in timeline]
        if self.linked is None:
            self.player.stop()
            self._set_player.set_speed(self._rec_player.speed)
        self.rec = None
        self.linked = linked
        self.player = self._set_player
        for w in (self.tags, self.notes, self.clear_crop_btn):
            w.hide()
        self.crop_label.setText("")
        self.title.setEnabled(True)
        self.title.setToolTip("Rename this set (F2)")
        self.context.setToolTip("Used as context when each part is transcribed, together with the dictionary.")
        if not self.title.hasFocus():
            self.title.setText(linked.title)
        contexts = {r.meta.context_line for r in parts}
        if not self.context.hasFocus():
            self.context.setText(contexts.pop() if len(contexts) == 1 else "")
        self.context.setEnabled(True)
        first, last = parts[0].meta.created, parts[-1].meta.created
        span = fmt_date(first) + (f" to {fmt_date(last).split(' ')[-1]}" if first[:10] == last[:10] else
                                  f" to {fmt_date(last)}")
        self.subtitle.setText(f"{span} · {sets.summary(linked, parts)}")
        self.file_info.setText("")
        self.stats.setText("")
        playable = any(p.rec.audio_path is not None and p.rec.audio_path.exists() for p in timeline)
        for w in (self.play_btn, self.speed_btn, self.volume_btn, self.volume, self.volume_label, self.wave):
            w.setEnabled(playable)
        self._show_volume()
        if same and sig == getattr(self, "_set_sig", None):
            self.wave.markers = self._set_markers(timeline)
            self.wave.update()
            return
        self._set_sig = sig
        self.parts = timeline
        self._set_player.load(timeline)
        self._sync_play_icon()
        self.wave.editable = False
        self.wave.dividers = [p.offset for p in timeline[1:]]
        self.wave.placeholder = "Drawing waveform…"
        self.wave.set_recording(sets.total(timeline), None, None, (), self._set_markers(timeline))
        self.wave.set_peaks(None)
        sid = linked.id
        jobs = [(p.rec.audio_path, p.rec.meta.sha256, p.start, p.length, bool(p.rec.meta.tracks))
                for p in timeline]

        def compute():
            chunks = []
            for path, key, start, length, mix in jobs:
                n = int(round(length * peaks_mod.BUCKETS_PER_SECOND))
                try:
                    pk = peaks_mod.compute(path, key, mix) if path is not None and path.exists() else None
                except Exception:  # noqa: BLE001 - a part without a waveform still has its place
                    pk = None
                a = int(round(start * peaks_mod.BUCKETS_PER_SECOND))
                chunk = pk[a:a + n] if pk is not None else np.zeros((0, 2), dtype=np.int16)
                if len(chunk) < n:
                    chunk = np.concatenate([chunk, np.zeros((n - len(chunk), 2), dtype=chunk.dtype)])
                chunks.append(chunk)
            return np.concatenate(chunks) if chunks else None

        run_task(compute, on_done=lambda pk: self._set_peaks_ready(sid, pk),
                 on_error=lambda m: log.warning("waveform failed: %s", m))
        self._update_time()

    @staticmethod
    def _set_markers(timeline) -> list[dict]:
        out = []
        for p in timeline:
            for m in p.rec.meta.markers:
                if p.start <= m["at"] <= p.start + p.length:
                    out.append({"at": p.to_set(m["at"]), "note": m.get("note") or ""})
        return out

    def _set_peaks_ready(self, sid: str, pk):
        if self.linked is not None and self.linked.id == sid:
            self.wave.set_peaks(pk)

    def set_recording(self, rec: Recording | None):
        self._leave_set()
        same = rec is not None and self.rec is not None and rec.id == self.rec.id
        self.rec = rec
        playable = rec is not None and rec.meta.state == READY and rec.audio_path is not None and rec.audio_path.exists()
        for w in (self.play_btn, self.speed_btn, self.volume_btn, self.volume, self.volume_label, self.export_btn,
                  self.wave):
            w.setEnabled(playable)
        self._show_volume()
        self.title.setEnabled(rec is not None)
        for w in (self.context, self.tags, self.notes):
            w.setEnabled(rec is not None)
        if rec is None:
            self.player.load(None, 0)
            self._sync_play_icon()
            self._loaded_sha = None
            self.title.setText("")
            self.context.setText("")
            self.tags.set_tags([])
            self.notes.set_text("")
            self.subtitle.setText("")
            self.file_info.setText("")
            self.stats.setText("")
            self.wave.placeholder = ""
            self.wave.set_recording(0, None, None)
            self.wave.set_peaks(None)
            self._update_crop_label()
            self._update_time()
            return
        if not self.title.hasFocus():
            self.title.setText(rec.meta.title)
        if not self.context.hasFocus():
            self.context.setText(rec.meta.context_line)
        self.tags.set_tags(rec.meta.tags)
        self.notes.set_text(rec.meta.notes)
        bits = [fmt_date(rec.meta.created)]
        if rec.meta.duration:
            bits.append(fmt_length(rec.meta.duration))
        n = len(rec.speaker_numbers()) if not rec.meta.speakers_off else 0
        if n > 1:
            bits.append(f"{n} speakers")
        self.subtitle.setText(" · ".join(bits))
        facts = [rec.meta.source or rec.meta.audio or ""]
        if rec.meta.recovered:
            facts.append("Recovered after a crash")
        interruptions = [g for g in rec.meta.gaps if g.get("kind") == "interruption"]
        if interruptions:
            facts.append(f"{len(interruptions)} capture interruption{'s' if len(interruptions) > 1 else ''}")
        self.file_info.setText("\n".join(f for f in facts if f))
        self.stats.setText(statistics(rec).replace("  ·  ", "\n"))
        if same and self._loaded_sha == rec.meta.sha256 and playable:
            self.wave.crop_start, self.wave.crop_end = rec.meta.crop_start, rec.meta.crop_end
            if self.wave._drag != "marker":
                self.wave.markers = [dict(m) for m in rec.meta.markers]
            self._update_crop_label()
            self.wave.update()
            return
        self.player.stop()
        self._sync_play_icon()
        if not playable:
            self.player.load(None, 0)
            self._loaded_sha = None
            self.wave.placeholder = ("Recording in progress" if rec.meta.state == "recording"
                                     else rec.meta.error or "No audio")
            self.wave.set_recording(0, None, None)
            self.wave.set_peaks(None)
            self._update_crop_label()
            self._update_time()
            return
        self._loaded_sha = rec.meta.sha256
        self.player.load(rec.audio_path, rec.meta.duration or 0, bool(rec.meta.tracks))
        if rec.meta.crop_start:
            self.player.seek(rec.meta.crop_start)
        gaps = [g["at"] for g in interruptions if "at" in g]
        self.wave.placeholder = "Drawing waveform…"
        self.wave.set_recording(rec.meta.duration or 0, rec.meta.crop_start, rec.meta.crop_end, gaps,
                                rec.meta.markers)
        self.wave.set_peaks(None)
        rid, path, key = rec.id, rec.audio_path, rec.meta.sha256
        run_task(peaks_mod.compute, path, key, bool(rec.meta.tracks),
                 on_done=lambda pk: self._peaks_ready(rid, pk),
                 on_error=lambda m: log.warning("waveform failed: %s", m))
        self._update_crop_label()
        self._update_time()

    def _peaks_ready(self, rid: str, pk):
        if self.rec is not None and self.rec.id == rid:
            self.wave.set_peaks(pk)

    def _commit_title(self):
        if self.linked is not None:
            new = self.title.text().strip()
            if not new:
                self.title.setText(self.linked.title)
            elif new != self.linked.title:
                self.linked.title = new
                self.set_renamed.emit(self.linked.id, new)
            return
        if self.rec is None:
            return
        new = self.title.text().strip()
        if not new:
            self.title.setText(self.rec.meta.title)
            return
        if new != self.rec.meta.title:
            self.rec.update(title=new, title_auto=False)  # the user's title is never replaced
            self.renamed.emit(self.rec.id, new)

    def _commit_tags(self, tags: list):
        if self.rec is not None:
            self.tags.set_tags(self.rec.set_tags(tags))
            self.meta_changed.emit(self.rec.id)

    def _commit_notes(self, text: str):
        if self.rec is not None and text != self.rec.meta.notes:
            self.rec.update(notes=text)
            self.meta_changed.emit(self.rec.id)

    def _commit_context(self):
        line = " ".join(self.context.text().split())
        if self.linked is not None:
            # A burst has the same people throughout: the line goes to every part.
            for p in self.parts:
                if p.rec.meta.context_line != line:
                    p.rec.update(context_line=line)
            return
        if self.rec is None:
            return
        if line != self.rec.meta.context_line:
            self.rec.update(context_line=line)

    def focus_title(self):
        self.title.setFocus()
        self.title.selectAll()

    # ---- crop ----
    def _crop_changed(self, start, end):
        if self.rec is None or self.linked is not None:
            return
        self.rec.update(crop_start=round(start, 2) if start else None,
                        crop_end=round(end, 2) if end is not None else None)
        self._update_crop_label()
        self.crop_saved.emit(self.rec.id)

    def _markers_edited(self, markers: list):
        if self.rec is None:
            return
        self.rec.set_markers(markers)
        self.markers_changed.emit(self.rec.id)

    def add_marker_at_playhead(self):
        if self.linked is not None:
            self.message.emit("Markers belong to one part: select the part to add one.")
            return
        if self.rec is None or not self.wave.isEnabled():
            return
        at = self.player.position()
        self.wave.add_marker(at)
        self.message.emit(f"Marker at {fmt_duration(at)}. Right-click it on the waveform to add a note.")

    def jump_marker(self, direction: int):
        """Seek to the next (1) or previous (-1) marker, and keep playing if playing."""
        markers = self.wave.markers if self.linked is not None else (self.rec.meta.markers if self.rec else [])
        if not markers:
            return
        pos = self.player.position()
        ats = [m["at"] for m in markers]
        if direction > 0:
            target = next((a for a in ats if a > pos + 0.25), None)
        else:
            # Pressed again right after a jump, it goes one further back, as in a music player.
            target = next((a for a in reversed(ats) if a < pos - 1.5), None)
        if target is not None:
            self.seek(target)

    def clear_crop(self):
        self.wave.crop_start = self.wave.crop_end = None
        self.wave.update()
        self._crop_changed(None, None)

    def _update_crop_label(self):
        rec = self.rec
        cropped = rec is not None and (rec.meta.crop_start or rec.meta.crop_end is not None)
        self.clear_crop_btn.setVisible(bool(cropped))
        if cropped:
            s = rec.meta.crop_start or 0
            e = rec.meta.crop_end if rec.meta.crop_end is not None else (rec.meta.duration or 0)
            self.crop_label.setText(f"Crop {fmt_duration(s)}–{fmt_duration(e)}")
        else:
            self.crop_label.setText("")
        self.crop_label.setVisible(bool(cropped))

    # ---- playback ----
    def _shown(self) -> bool:
        return self.rec is not None or self.linked is not None

    def play_span(self, start: float, end: float) -> None:
        """Play one passage and stop at its end (editing with the audio)."""
        if not self._shown() or not self.play_btn.isEnabled():
            return
        self._span = (start, end)
        self.player.play(start, end)
        self._sync_play_icon()

    def seek_shown(self, sec: float) -> None:
        """Show `sec` as the position (waveform and time) without touching playback."""
        self.wave.set_position(sec)
        self.time.setText(fmt_duration(sec))

    def stop_span(self) -> None:
        self._span = None
        if self.player.playing:
            self.player.pause()
        self._sync_play_icon()

    def toggle_play(self):
        if not self._shown() or not self.play_btn.isEnabled():
            return
        self._span = None
        if self.player.playing:
            self.player.pause()
        elif self.linked is not None:
            self.player.play(None, None)  # from the playhead; from the start once at the end
        else:
            start, end = self.rec.effective_span()
            pos = self.player.position()
            if pos < start - 0.05 or (end is not None and pos >= end - 0.05) or \
                    (self.player.duration and pos >= self.player.duration - 0.05):
                pos = start
            self.player.play(pos, end)
        self._sync_play_icon()

    def seek(self, sec: float):
        if not self._shown():
            return
        self.player.seek(sec)
        self.wave.set_position(sec)
        self._update_time()
        self.position_changed.emit(sec)

    def _sync_play_icon(self):
        playing = self.player.playing
        if playing != getattr(self, "_shown_playing", False):
            self._shown_playing = playing
            motion.fade(self.play_btn, 1.0, motion.FAST, start=0.35)  # the icon crosses over
        self.play_btn.setIcon(icon("pause" if playing else "play", "on_accent"))
        self.play_btn.setAccessibleName("Pause" if playing else "Play")
        if playing:
            self._timer.start()
        else:
            self._timer.stop()
            self._tick()

    def _tick(self):
        if not self._shown():
            return
        if self.player.poll():
            self._sync_play_icon()
            if self.player.error:
                self.message.emit(f"Playback failed: {self.player.error}")
            elif self._span is not None:
                self._span = None
                self.span_finished.emit()
        pos = self.player.position()
        self.wave.set_position(pos)
        self._update_time()
        self.position_changed.emit(pos)

    def _update_time(self):
        dur = (self.rec.meta.duration if self.rec else 0) or self.player.duration
        if self.linked is not None:
            dur = self.player.duration
        self.time.setText(fmt_duration(self.player.position()))
        self.total.setText(fmt_duration(dur))

    def speed_value(self) -> float:
        return self.speed.currentData()

    def set_speed(self, value: float):
        idx = self.speed.findData(value)
        if idx >= 0:
            self.speed.setCurrentIndex(idx)

    # ---- volume ----
    def _volume_key(self) -> str | None:
        if self.linked is not None:
            return self.linked.id
        return self.rec.id if self.rec is not None else None

    def _show_volume(self):
        """Put the shown recording's own volume on the slider and the player."""
        self._volume_timer.stop()
        value = self.volumes.get(self._volume_key(), 1.0)
        if self.volume.value() != round(value * 100):
            self.volume.blockSignals(True)
            self.volume.setValue(round(value * 100))
            self.volume.blockSignals(False)
        self.volume_label.setText(f"{self.volume.value()}%")
        self._show_volume_btn()
        self.player.set_volume(value)

    def _show_volume_btn(self):
        pct = self.volume.value()
        self.volume_btn.setText("" if pct == 100 else f"{pct}%")

    def _volume_moved(self, pct: int):
        # Stored at once, so a refresh of the same recording during a drag keeps the new value.
        self.volume_label.setText(f"{pct}%")
        self._show_volume_btn()
        key = self._volume_key()
        if key is not None:
            if pct == 100:
                self.volumes.pop(key, None)
            else:
                self.volumes[key] = pct / 100
        self._volume_timer.start()

    def _apply_volume(self):
        self.player.set_volume(self.volume.value() / 100)

    def volume_value(self) -> float:
        return self.volume.value() / 100

    def eventFilter(self, obj, event):
        if obj is self.volume and event.type() == QEvent.Type.MouseButtonDblClick:
            self.volume.setValue(100)
            return True
        return super().eventFilter(obj, event)

    def is_playing(self) -> bool:
        return self.player.playing
