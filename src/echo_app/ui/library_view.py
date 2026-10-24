"""Library list: model with incremental refresh, live status, and a compact row painter."""

from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from .. import recorder
from ..library import (FAILED, NEEDS_FINALIZE, READY, RECORDING, T_DONE, T_FAILED, T_QUEUED, T_RUNNING,
                       Library, Recording)
from . import theme
from .common import fmt_date, fmt_duration, fmt_eta

ROLE_REC = Qt.ItemDataRole.UserRole + 1
ROLE_STATUS = Qt.ItemDataRole.UserRole + 2
ROLE_HEADER = Qt.ItemDataRole.UserRole + 3

HEADER = "§"  # row ids starting with this are month headings
GROUP_AFTER = 30  # recordings in the list before it is grouped by month...
GROUP_MONTHS = 2  # ...or months it spans
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")

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
        if rec.is_edited():
            return Status("Edited", K_EDITED, None, m.recovered)
        n = sum(1 for s in (rec.transcript() or {}).get("segments", []) if s.get("flags"))
        return Status(f"Transcribed · ⚑ {n}" if n else "Transcribed", K_DONE, None, m.recovered)
    return Status("", K_NONE, None, m.recovered)


class LibraryModel(QAbstractListModel):
    recordings_changed = Signal(list)  # ids whose folders changed (not the first load)

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.library = library
        self._all: dict[str, Recording] = {}
        self._mtimes: dict[str, float] = {}
        self._status: dict[str, Status] = {}
        self._rows: list[str] = []
        self._filter: set[str] | None = None
        self._loaded = False

    # ---- Qt model API ----
    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        rid = self._rows[index.row()]
        if rid.startswith(HEADER):
            if role in (Qt.ItemDataRole.DisplayRole, ROLE_HEADER):
                y, m = rid[1:].split("-")
                return f"{MONTHS[int(m) - 1]} {y}"
            return None
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

    def flags(self, index):
        if index.isValid() and index.row() < len(self._rows) and self._rows[index.row()].startswith(HEADER):
            return Qt.ItemFlag.NoItemFlags  # headings are neither selectable nor reachable by keys
        return super().flags(index)

    # ---- data ----
    def first_row(self) -> int:
        """The first row holding a recording, or -1."""
        return next((i for i, r in enumerate(self._rows) if not r.startswith(HEADER)), -1)

    def nearest_row(self, row: int) -> int:
        """The recording row at or before `row` (after it if none), for keeping a selection."""
        rows = [i for i, r in enumerate(self._rows) if not r.startswith(HEADER)]
        if not rows:
            return -1
        before = [i for i in rows if i <= row]
        return before[-1] if before else rows[0]

    def tag_counts(self) -> list[tuple[str, int]]:
        """(tag, recordings) over the whole library, most used first; spelled as most often typed."""
        from ..library import fold_tag

        totals: dict[str, dict[str, int]] = {}
        for rec in self._all.values():
            for t in rec.meta.tags:
                spellings = totals.setdefault(fold_tag(t), {})
                spellings[t] = spellings.get(t, 0) + 1
        out = [(max(sp, key=sp.get), sum(sp.values())) for sp in totals.values()]
        return sorted(out, key=lambda x: (-x[1], fold_tag(x[0])))

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
        if changed_ids and self._loaded:
            self.recordings_changed.emit(changed_ids)
        self._loaded = True
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
        months = [self._all[r].meta.created[:7] for r in ids]
        if len(ids) > GROUP_AFTER or len(set(months)) > GROUP_MONTHS:
            grouped = []
            last = None
            for rid, month in zip(ids, months):
                if month != last:
                    grouped.append(HEADER + month)
                    last = month
                grouped.append(rid)
            ids = grouped
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
    """Rows on the deep sidebar: title, date and length, and a status that only shouts when it matters."""

    PAD = 10
    MARGIN = 8  # gap between the row card and the list edges

    def sizeHint(self, option, index) -> QSize:
        fm = QFontMetrics(option.font)
        if index.data(ROLE_HEADER):
            return QSize(200, fm.height() + 14)
        return QSize(200, fm.height() * 2 + self.PAD * 2 + 8)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        heading = index.data(ROLE_HEADER)
        if heading:
            p.save()
            p.setFont(theme.display_font(0.78, QFont.Weight.ExtraBold))
            p.setPen(QColor(theme.current().foam))
            r = option.rect.adjusted(self.MARGIN + 6, 6, -self.MARGIN, 0)
            p.drawText(r, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, heading.upper())
            p.restore()
            return
        rec: Recording = index.data(ROLE_REC)
        st: Status | None = index.data(ROLE_STATUS)
        if rec is None:
            return
        t = theme.current()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        card = QRectF(option.rect).adjusted(self.MARGIN, 2, -self.MARGIN, -2)
        if selected or hover:
            p.setPen(theme.color("on_deep", 0.22) if selected else Qt.PenStyle.NoPen)
            p.setBrush(theme.color("on_deep", 0.14 if selected else 0.06))
            p.drawRoundedRect(card, 12, 12)
        live = st is not None and st.kind == K_RECORDING
        r = card.adjusted(self.PAD + 2, self.PAD - 2, -self.PAD, -self.PAD + 2).toRect()
        fm = QFontMetrics(option.font)
        bold = theme.display_font(1.0, QFont.Weight.Bold)
        bfm = QFontMetrics(bold)
        x = r.left()
        if live:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.coral))
            d = 8
            p.drawEllipse(x, r.top() + (bfm.height() - d) // 2, d, d)
            x += d + 7
        # Line 1: title
        p.setFont(bold)
        p.setPen(QColor(t.on_deep))
        title_rect = QRect(x, r.top(), r.right() - x, bfm.height())
        p.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   bfm.elidedText(rec.meta.title, Qt.TextElideMode.ElideRight, title_rect.width()))
        # Line 2: date · duration      status
        y2 = r.top() + bfm.height() + 3
        p.setFont(option.font)
        left = fmt_date(rec.meta.created)
        if rec.meta.duration and not live:
            left += f"  ·  {fmt_duration(rec.meta.duration)}"
        status_text = st.text if st else ""
        if st and st.recovered and st.kind != K_RECORDING:
            status_text = ("Recovered · " + status_text) if status_text else "Recovered"
        kind = st.kind if st else K_NONE
        pill = kind in (K_RECORDING, K_BUSY, K_WAIT, K_ERROR)
        small = QFont(option.font)
        if pill:
            small = theme.display_font(0.82, QFont.Weight.Bold)
        sfm = QFontMetrics(small)
        sw = sfm.horizontalAdvance(status_text) + (16 if pill else 0)
        avail = r.width() - sw - 10
        p.setPen(QColor(t.on_deep_muted))
        p.drawText(QRect(r.left(), y2, max(0, avail), fm.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(left, Qt.TextElideMode.ElideRight, max(0, avail)))
        if status_text:
            srect = QRectF(r.right() - sw, y2 + (fm.height() - sfm.height() - 4) / 2, sw, sfm.height() + 4)
            if pill:
                fill, ink = {K_RECORDING: (QColor(t.coral_deep), QColor("#ffffff")),
                             K_ERROR: (QColor(t.amber), QColor(t.deep_top)),
                             K_BUSY: (theme.color("foam", 0.22), QColor(t.foam)),
                             K_WAIT: (theme.color("on_deep", 0.12), QColor(t.on_deep))}[kind]
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(fill)
                p.drawRoundedRect(srect, srect.height() / 2, srect.height() / 2)
                p.setPen(ink)
            else:
                p.setPen(QColor(t.foam) if kind == K_EDITED else QColor(t.on_deep_muted))
            p.setFont(small)
            p.drawText(srect, Qt.AlignmentFlag.AlignCenter if pill else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       status_text)
        # Progress along the bottom of the row card
        if st and st.progress is not None and st.kind == K_BUSY:
            bar = QRectF(card.left() + 12, card.bottom() - 4, card.width() - 24, 3)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("on_deep", 0.12))
            p.drawRoundedRect(bar, 1.5, 1.5)
            bar.setWidth(bar.width() * max(0.02, min(1.0, st.progress)))
            p.setBrush(QColor(t.foam))
            p.drawRoundedRect(bar, 1.5, 1.5)
        p.restore()
