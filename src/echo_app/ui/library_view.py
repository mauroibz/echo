"""Library list: model with incremental refresh, live status, and a compact row painter."""

from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from .. import recorder
from ..library import (FAILED, NEEDS_FINALIZE, READY, RECORDING, T_DONE, T_FAILED, T_QUEUED, T_RUNNING,
                       Library, Recording)
from .common import RECORD_RED, fmt_date, fmt_duration, fmt_eta

ROLE_REC = Qt.ItemDataRole.UserRole + 1
ROLE_STATUS = Qt.ItemDataRole.UserRole + 2

# Status kinds drive colors.
K_RECORDING, K_BUSY, K_DONE, K_EDITED, K_WAIT, K_ERROR, K_NONE = (
    "recording", "busy", "done", "edited", "wait", "error", "none")


@dataclass
class Status:
    text: str
    kind: str
    progress: float | None = None  # 0..1 for a thin bar
    recovered: bool = False


def status_of(rec: Recording) -> Status:
    m = rec.meta
    if m.state == RECORDING:
        if rec.takes_dir.is_dir():
            sess = recorder.Session(rec)
            if sess.alive():
                st = sess.status()
                if st.get("state") == recorder.S_FINALIZING:
                    return Status("Saving…", K_BUSY)
                label = "Paused" if st.get("state") == recorder.S_PAUSED else "Recording"
                return Status(f"{label} {fmt_duration(st.get('elapsed'))}", K_RECORDING)
        return Status("Interrupted, recovering…", K_WAIT)
    if m.state in (NEEDS_FINALIZE, FAILED):
        return Status("Needs attention", K_ERROR, recovered=m.recovered)
    if m.state != READY:
        return Status(m.state, K_NONE)
    t = rec.transcript_status()
    if t == T_RUNNING:
        p = rec.progress() or {}
        stage = p.get("stage")
        if stage == "loading":
            return Status("Starting transcription…", K_BUSY, 0.0, m.recovered)
        if stage == "detecting":
            return Status("Finding speech…", K_BUSY, 0.0, m.recovered)
        frac = (p.get("done", 0) / p["total"]) if p.get("total") else 0.0
        eta = fmt_eta(p.get("eta_s"))
        return Status(f"Transcribing {frac:.0%}" + (f" · {eta}" if eta else ""), K_BUSY, frac, m.recovered)
    if t == T_QUEUED:
        return Status("Waiting to transcribe", K_WAIT, None, m.recovered)
    if t == T_FAILED:
        return Status("Transcription failed", K_ERROR, None, m.recovered)
    if t == T_DONE:
        return Status("Edited" if rec.is_edited() else "Transcribed", K_EDITED if rec.is_edited() else K_DONE,
                      None, m.recovered)
    return Status("", K_NONE, None, m.recovered)


class LibraryModel(QAbstractListModel):
    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.library = library
        self._all: dict[str, Recording] = {}
        self._mtimes: dict[str, float] = {}
        self._status: dict[str, Status] = {}
        self._rows: list[str] = []
        self._filter: set[str] | None = None

    # ---- Qt model API ----
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        rid = self._rows[index.row()]
        rec = self._all.get(rid)
        if rec is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return rec.meta.title
        if role == ROLE_REC:
            return rec
        if role == ROLE_STATUS:
            return self._status.get(rid)
        if role == Qt.ItemDataRole.ToolTipRole:
            st = self._status.get(rid)
            tip = f"{rec.meta.title}\n{fmt_date(rec.meta.created)} · {fmt_duration(rec.meta.duration)}"
            if rec.meta.source:
                tip += f"\n{rec.meta.source}"
            if st and st.text:
                tip += f"\n{st.text}"
            if rec.meta.error:
                tip += f"\n{rec.meta.error}"
            elif rec.transcript_status() == T_FAILED and rec.error_text():
                tip += f"\n{rec.error_text()}"
            return tip
        return None

    # ---- data ----
    def recording(self, row: int) -> Recording | None:
        if 0 <= row < len(self._rows):
            return self._all.get(self._rows[row])
        return None

    def row_of(self, rid: str) -> int:
        try:
            return self._rows.index(rid)
        except ValueError:
            return -1

    def set_filter(self, ids: set[str] | None) -> None:
        self._filter = ids
        self._rebuild_rows()

    def refresh(self) -> None:
        """Reload changed folders; cheap enough to run every second."""
        rdir = self.library.recordings_dir
        seen: dict[str, float] = {}
        try:
            entries = list(os.scandir(rdir))
        except FileNotFoundError:
            entries = []
        for e in entries:
            if e.is_dir() and not e.name.startswith("."):
                try:
                    seen[e.name] = e.stat().st_mtime
                except FileNotFoundError:
                    continue
        changed_ids = []
        for rid, mtime in seen.items():
            if self._mtimes.get(rid) != mtime or rid not in self._all:
                rec = self.library.get(rid)
                if rec is None:
                    continue
                self._all[rid] = rec
                self._mtimes[rid] = mtime
                changed_ids.append(rid)
        removed = [rid for rid in self._all if rid not in seen]
        for rid in removed:
            self._all.pop(rid, None)
            self._mtimes.pop(rid, None)
            self._status.pop(rid, None)
        # Live rows (recording, transcribing) change without a folder mtime change on every tick.
        for rid, rec in self._all.items():
            if rid in changed_ids or rec.meta.state == RECORDING:
                self._status[rid] = status_of(rec)
        if changed_ids or removed or set(self._rows) - set(self._all):
            self._rebuild_rows()
        else:
            for rid, rec in self._all.items():
                if rec.meta.state == RECORDING:
                    row = self.row_of(rid)
                    if row >= 0:
                        idx = self.index(row)
                        self.dataChanged.emit(idx, idx)

    def reload(self, rid: str) -> None:
        rec = self.library.get(rid)
        if rec is None:
            return
        self._all[rid] = rec
        self._mtimes.pop(rid, None)
        self._status[rid] = status_of(rec)
        row = self.row_of(rid)
        if row >= 0:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx)

    def _rebuild_rows(self) -> None:
        ids = [rid for rid in self._all if self._filter is None or rid in self._filter
               or self._all[rid].meta.state == RECORDING]
        ids.sort(key=lambda r: (self._all[r].meta.created, r), reverse=True)
        if ids == self._rows:
            if self._rows:
                self.dataChanged.emit(self.index(0), self.index(len(self._rows) - 1))
            return
        self.beginResetModel()
        self._rows = ids
        self.endResetModel()

    @property
    def total(self) -> int:
        return len(self._all)


class RowDelegate(QStyledItemDelegate):
    PAD = 8

    def sizeHint(self, option, index) -> QSize:
        fm = QFontMetrics(option.font)
        return QSize(200, fm.height() * 2 + self.PAD * 2 + 4)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        rec: Recording = index.data(ROLE_REC)
        st: Status | None = index.data(ROLE_STATUS)
        if rec is None:
            return
        p.save()
        style = option.widget.style() if option.widget else None
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, p, option.widget)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        pal = option.palette
        fg = pal.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text)
        dim = QColor(fg)
        dim.setAlpha(150)
        r = option.rect.adjusted(self.PAD + 2, self.PAD, -self.PAD, -self.PAD)
        fm = QFontMetrics(option.font)
        bold = QFont(option.font)
        bold.setWeight(QFont.Weight.DemiBold)
        bfm = QFontMetrics(bold)
        live = st is not None and st.kind == K_RECORDING
        x = r.left()
        if live:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(RECORD_RED)
            d = 8
            p.drawEllipse(x, r.top() + (bfm.height() - d) // 2, d, d)
            x += d + 6
        # Line 1: title
        p.setFont(bold)
        p.setPen(fg)
        title_rect = QRect(x, r.top(), r.right() - x, bfm.height())
        p.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   bfm.elidedText(rec.meta.title, Qt.TextElideMode.ElideRight, title_rect.width()))
        # Line 2: date · duration      status
        y2 = r.top() + bfm.height() + 2
        p.setFont(option.font)
        left = fmt_date(rec.meta.created)
        if rec.meta.duration and not live:
            left += f" · {fmt_duration(rec.meta.duration)}"
        status_text = st.text if st else ""
        if st and st.recovered and st.kind != K_RECORDING:
            status_text = ("Recovered · " + status_text) if status_text else "Recovered"
        sw = fm.horizontalAdvance(status_text)
        avail = r.width() - sw - 12
        p.setPen(dim)
        p.drawText(QRect(r.left(), y2, max(0, avail), fm.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(left, Qt.TextElideMode.ElideRight, max(0, avail)))
        if status_text:
            color = {K_RECORDING: RECORD_RED, K_ERROR: QColor("#d9822b") if not selected else fg,
                     K_BUSY: pal.color(QPalette.ColorRole.Link) if not selected else fg}.get(st.kind if st else K_NONE, dim)
            p.setPen(color)
            status_rect = QRect(r.right() - sw, y2, sw, fm.height())
            p.drawText(status_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, status_text)
        # Progress bar along the bottom edge
        if st and st.progress is not None and st.kind == K_BUSY:
            bar = QRect(option.rect.left() + self.PAD, option.rect.bottom() - 3, option.rect.width() - 2 * self.PAD, 2)
            track = QColor(fg)
            track.setAlpha(40)
            p.fillRect(bar, track)
            bar.setWidth(int(bar.width() * max(0.02, min(1.0, st.progress))))
            p.fillRect(bar, pal.color(QPalette.ColorRole.Link) if not selected else fg)
        p.restore()
