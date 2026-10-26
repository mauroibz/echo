"""Library list: model with incremental refresh, live status, and a compact row painter."""

from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from .. import recorder, sets
from ..library import (FAILED, NEEDS_FINALIZE, READY, RECORDING, T_DONE, T_FAILED, T_QUEUED, T_RUNNING,
                       Library, Recording)
from . import theme
from .common import fmt_date, fmt_duration, fmt_eta
from .common import icon as tinted_icon

ROLE_REC = Qt.ItemDataRole.UserRole + 1
ROLE_STATUS = Qt.ItemDataRole.UserRole + 2
ROLE_HEADER = Qt.ItemDataRole.UserRole + 3
ROLE_KIND = Qt.ItemDataRole.UserRole + 4  # ROW_* below
ROLE_SET = Qt.ItemDataRole.UserRole + 5  # (LinkedSet, its present parts) on a set row
ROLE_PART = Qt.ItemDataRole.UserRole + 6  # (part number from 1, expanded set id) on a part row
ROLE_SNIPPET = Qt.ItemDataRole.UserRole + 7  # "Ana: …el precio sube…" under a speaker search result

ROW_HEADER, ROW_REC, ROW_SET, ROW_PART = "header", "rec", "set", "part"

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
        if stage == "speakers":
            frac = (p.get("done", 0) / p["total"]) if p.get("total") else 0.0
            return Status("Telling speakers apart…", K_BUSY, frac, m.recovered)
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


def set_status(statuses: list[Status | None]) -> Status:
    """One status for a set: what most needs attention among its parts."""
    sts = [st for st in statuses if st is not None]
    kinds = [st.kind for st in sts]
    if K_RECORDING in kinds:
        return next(st for st in sts if st.kind == K_RECORDING)
    if K_ERROR in kinds:
        n = kinds.count(K_ERROR)
        return Status("Needs attention" if n == 1 else f"{n} need attention", K_ERROR)
    busy = [st for st in sts if st.kind in (K_BUSY, K_WAIT)]
    if busy:
        running = [st for st in busy if st.kind == K_BUSY and st.progress is not None]
        frac = running[0].progress if running else None
        left = len(busy)
        return Status(f"Transcribing · {left} left" if running else f"Waiting · {left} to transcribe",
                      K_BUSY if running else K_WAIT, frac)
    if kinds and all(k in (K_DONE, K_EDITED) for k in kinds):
        if K_EDITED in kinds:
            return Status("Edited", K_EDITED)
        flags = sum(int(st.text.rsplit("⚑", 1)[1]) for st in sts if "⚑" in st.text)
        return Status(f"Transcribed · ⚑ {flags}" if flags else "Transcribed", K_DONE)
    return Status("", K_NONE)


class LibraryModel(QAbstractListModel):
    recordings_changed = Signal(list)  # ids whose folders changed (not the first load)
    sets_changed = Signal()  # a set file was added, changed or removed
    # A drag in the list: (ids dragged, row dropped onto or None, set dropped into or None, the part
    # it goes before). Handled by the window, which changes the set files.
    drop_requested = Signal(list, object, object, object)
    MIME = "application/x-echo-ids"

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.library = library
        self._all: dict[str, Recording] = {}
        self._mtimes: dict[str, float] = {}
        self._status: dict[str, Status] = {}
        self._rows: list[str] = []
        self._filter: set[str] | None = None
        self._snippets: dict[str, str] = {}
        self._loaded = False
        self._sets: dict[str, sets.LinkedSet] = {}
        self._sets_sig: tuple = ()
        self._parts: dict[str, list[str]] = {}  # set id -> present members (two or more), in order
        self._member_of: dict[str, str] = {}  # recording id -> set id, for those sets
        self.expanded: set[str] = set()

    # ---- Qt model API ----
    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        rid = self._rows[index.row()]
        if role == ROLE_KIND:
            return self.kind(index.row())
        if rid.startswith(HEADER):
            if role in (Qt.ItemDataRole.DisplayRole, ROLE_HEADER):
                y, m = rid[1:].split("-")
                return f"{MONTHS[int(m) - 1]} {y}"
            return None
        if rid in self._parts:
            return self._set_data(rid, role)
        if role == ROLE_PART:
            sid = self._member_of.get(rid)
            return (self._parts[sid].index(rid) + 1, sid) if sid else None
        rec = self._all.get(rid)
        if rec is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return rec.meta.title
        if role == ROLE_REC:
            return rec
        if role == ROLE_STATUS:
            return self._status.get(rid)
        if role == ROLE_SNIPPET:
            return self._snippets.get(rid)
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

    def _set_data(self, sid: str, role):
        st = self._sets[sid]
        parts = [self._all[m] for m in self._parts[sid]]
        if role == Qt.ItemDataRole.DisplayRole:
            return st.title
        if role == ROLE_SET:
            return st, parts
        if role == ROLE_STATUS:
            return set_status([self._status.get(m) for m in self._parts[sid]])
        if role == Qt.ItemDataRole.ToolTipRole:
            lines = [st.title, sets.summary(st, parts)]
            lines += [f"{k}. {r.meta.title}" for k, r in enumerate(parts, 1)]
            return "\n".join(lines)
        return None

    def kind(self, row: int) -> str | None:
        if not 0 <= row < len(self._rows):
            return None
        rid = self._rows[row]
        if rid.startswith(HEADER):
            return ROW_HEADER
        if rid in self._parts:
            return ROW_SET
        return ROW_PART if rid in self._member_of else ROW_REC

    def linked_set(self, row: int) -> tuple[sets.LinkedSet, list[Recording]] | None:
        """The set and its present parts on a set row."""
        if self.kind(row) != ROW_SET:
            return None
        sid = self._rows[row]
        return self._sets[sid], [self._all[m] for m in self._parts[sid]]

    def set_of(self, rid: str) -> str | None:
        """The set a recording is shown in (two or more present members), or None."""
        return self._member_of.get(rid)

    def parts_of(self, sid: str) -> list[Recording]:
        return [self._all[m] for m in self._parts.get(sid, [])]

    def get_set(self, sid: str) -> sets.LinkedSet | None:
        return self._sets.get(sid) if sid in self._parts else None

    def set_expanded(self, sid: str, on: bool) -> None:
        if (sid in self.expanded) == on:
            return
        (self.expanded.add if on else self.expanded.discard)(sid)
        self._rebuild_rows()

    def is_expanded(self, sid: str) -> bool:
        return sid in self.expanded

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled  # between rows
        if index.row() < len(self._rows) and self._rows[index.row()].startswith(HEADER):
            return Qt.ItemFlag.NoItemFlags  # headings are neither selectable nor reachable by keys
        return super().flags(index) | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled

    # ---- drag and drop (linking) ----
    def mimeTypes(self):
        return [self.MIME]

    def mimeData(self, indexes):
        from PySide6.QtCore import QMimeData

        ids = [self._rows[i.row()] for i in sorted(indexes, key=lambda i: i.row())
               if 0 <= i.row() < len(self._rows) and not self._rows[i.row()].startswith(HEADER)]
        md = QMimeData()
        md.setData(self.MIME, "\n".join(ids).encode())
        return md

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def canDropMimeData(self, data, action, row, column, parent):
        return data.hasFormat(self.MIME)

    def dropMimeData(self, data, action, row, column, parent):
        if not data.hasFormat(self.MIME):
            return False
        ids = [i for i in bytes(data.data(self.MIME)).decode().split("\n") if i]
        if not ids:
            return False
        if parent.isValid():
            target, sid, before = self.row_id(parent.row()), None, None
        elif 0 <= row < len(self._rows) and self.kind(row) == ROW_PART:
            target, sid, before = None, self._member_of[self._rows[row]], self._rows[row]
        else:
            target, sid, before = None, None, None
        if target is not None and target.startswith(HEADER):
            return False
        # After the drop returns: the window rebuilds the list, which must not happen mid-drop.
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda: self.drop_requested.emit(ids, target, sid, before))
        return True

    # ---- data ----
    def first_row(self) -> int:
        """The first row holding a recording or a set, or -1."""
        return next((i for i, r in enumerate(self._rows) if not r.startswith(HEADER)), -1)

    def nearest_row(self, row: int) -> int:
        """The recording or set row at or before `row` (after it if none), for keeping a selection."""
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

    def category_totals(self) -> dict[str, int]:
        """Recordings carrying any tag of each category (folded), over the whole library."""
        from ..library import fold_tag, tag_category

        out: dict[str, int] = {}
        for rec in self._all.values():
            for cat in {fold_tag(c[0]) for t in rec.meta.tags if (c := tag_category(t))}:
                out[cat] = out.get(cat, 0) + 1
        return out

    def recording(self, row: int) -> Recording | None:
        """The recording on a recording or part row; None on headings and set rows."""
        if 0 <= row < len(self._rows):
            return self._all.get(self._rows[row])
        return None

    def row_id(self, row: int) -> str | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def row_of(self, rid: str) -> int:
        try:
            return self._rows.index(rid)
        except ValueError:
            return -1

    def set_filter(self, ids: set[str] | None, snippets: dict[str, str] | None = None) -> None:
        """Show only `ids` (None: all); `snippets` are lines of matching speech per recording."""
        self._filter = ids
        self._snippets = dict(snippets or {})
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
        sets_changed = self._load_sets()
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
        if sets_changed:
            self.sets_changed.emit()
        if changed_ids or removed or sets_changed or set(self._rows) - set(self._all) - set(self._parts):
            self._rebuild_rows()
        else:
            for rid, rec in self._all.items():
                if rec.meta.state == RECORDING:
                    row = self.row_of(rid)
                    if row >= 0:
                        idx = self.index(row)
                        self.dataChanged.emit(idx, idx)

    def _load_sets(self) -> bool:
        """Re-read the set files when any of them changed. Returns whether they did."""
        try:
            sig = tuple(sorted((e.name, e.stat().st_mtime_ns) for e in os.scandir(self.library.data_dir / sets.SETS)
                               if e.name.endswith(".json")))
        except FileNotFoundError:
            sig = ()
        if sig == self._sets_sig:
            return False
        self._sets_sig = sig
        self._sets = {st.id: st for st in sets.load_all(self.library)}
        return True

    def reload_sets(self) -> None:
        """After the window changed a set: show it now rather than on the next tick."""
        if self._load_sets():
            self.sets_changed.emit()
            self._rebuild_rows()

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
        visible = {rid for rid in self._all if self._filter is None or rid in self._filter
                   or self._all[rid].meta.state == RECORDING}
        self._parts = {}
        for sid, st in self._sets.items():
            present = [m for m in st.members if m in self._all]
            if len(present) >= 2:
                self._parts[sid] = present
        self._member_of = {m: sid for sid, ms in self._parts.items() for m in ms}
        # Top-level items: recordings outside sets, and sets with a visible part, placed by their newest part.
        top: list[tuple[str, str]] = [(self._all[r].meta.created, r) for r in visible if r not in self._member_of]
        shown_parts: dict[str, list[str]] = {}
        for sid, ms in self._parts.items():
            hits = [m for m in ms if m in visible]
            if hits:
                top.append((max(self._all[m].meta.created for m in ms), sid))
                # While filtering, a set shows the parts that match; otherwise all of them when expanded.
                shown_parts[sid] = hits if self._filter is not None else (ms if sid in self.expanded else [])
        top.sort(reverse=True)
        grouping = len(top) > GROUP_AFTER or len({c[:7] for c, _ in top}) > GROUP_MONTHS
        ids, last = [], None
        for created, key in top:
            if grouping and created[:7] != last:
                ids.append(HEADER + created[:7])
                last = created[:7]
            ids.append(key)
            ids.extend(shown_parts.get(key, []))
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

    INDENT = 22  # part rows sit under their set
    CHEVRON = 18

    def sizeHint(self, option, index) -> QSize:
        fm = QFontMetrics(option.font)
        if index.data(ROLE_HEADER):
            return QSize(200, fm.height() + 14)
        if index.data(ROLE_KIND) == ROW_PART:
            return QSize(200, fm.height() + 16)
        extra = fm.height() + 3 if index.data(ROLE_SNIPPET) else 0
        return QSize(200, fm.height() * 2 + self.PAD * 2 + 8 + extra)

    def chevron_rect(self, rect: QRect) -> QRect:
        """Where a set row's expand arrow is drawn (and clicked)."""
        card = rect.adjusted(self.MARGIN, 2, -self.MARGIN, -2)
        return QRect(card.right() - self.PAD - self.CHEVRON, card.top() + self.PAD - 3, self.CHEVRON + 6,
                     self.CHEVRON + 6)

    def _card(self, p: QPainter, option, card: QRectF) -> None:
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            p.setPen(theme.color("on_deep", 0.22) if selected else Qt.PenStyle.NoPen)
            p.setBrush(theme.color("on_deep", 0.14 if selected else 0.06))
            p.drawRoundedRect(card, 12, 12)

    def _paint_part(self, p: QPainter, option, index, rec: Recording, st: Status | None) -> None:
        t = theme.current()
        number, _sid = index.data(ROLE_PART) or (0, None)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(option.rect).adjusted(self.MARGIN + self.INDENT, 1, -self.MARGIN, -1)
        # The thread that ties parts to their set.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color("foam", 0.35))
        p.drawRoundedRect(QRectF(self.MARGIN + 9, option.rect.top(), 2, option.rect.height()), 1, 1)
        self._card(p, option, card)
        fm = QFontMetrics(option.font)
        r = card.adjusted(10, 0, -self.PAD, 0).toRect()
        p.setPen(QColor(t.foam))
        num = f"{number}"
        p.drawText(QRect(r.left(), r.top(), 16, r.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   num)
        busy = st is not None and st.kind in (K_RECORDING, K_BUSY, K_WAIT, K_ERROR)
        right = st.text if busy else fmt_duration(rec.meta.duration) if rec.meta.duration else ""
        rw = fm.horizontalAdvance(right)
        p.setPen(QColor(t.amber) if st is not None and st.kind == K_ERROR else QColor(t.on_deep_muted))
        p.drawText(QRect(r.right() - rw, r.top(), rw, r.height()), Qt.AlignmentFlag.AlignVCenter, right)
        x = r.left() + 18
        p.setPen(QColor(t.on_deep))
        p.drawText(QRect(x, r.top(), r.right() - rw - 10 - x, r.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(rec.meta.title, Qt.TextElideMode.ElideRight, max(0, r.right() - rw - 10 - x)))
        p.restore()

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
        kind = index.data(ROLE_KIND)
        st: Status | None = index.data(ROLE_STATUS)
        linked = index.data(ROLE_SET) if kind == ROW_SET else None
        rec: Recording = index.data(ROLE_REC)
        if kind == ROW_PART and rec is not None:
            self._paint_part(p, option, index, rec, st)
            return
        if rec is None and linked is None:
            return
        t = theme.current()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(option.rect).adjusted(self.MARGIN, 2, -self.MARGIN, -2)
        self._card(p, option, card)
        live = st is not None and st.kind == K_RECORDING
        r = card.adjusted(self.PAD + 2, self.PAD - 2, -self.PAD, -self.PAD + 2).toRect()
        fm = QFontMetrics(option.font)
        bold = theme.display_font(1.0, QFont.Weight.Bold)
        bfm = QFontMetrics(bold)
        x = r.left()
        right_edge = r.right()
        if linked is not None:
            sz = 16
            tinted_icon("set", "foam").paint(p, QRect(x, r.top() + (bfm.height() - sz) // 2, sz, sz))
            x += sz + 7
            chev = self.chevron_rect(option.rect)
            expanded = index.model().is_expanded(linked[0].id)
            tinted_icon("collapse" if expanded else "expand", "on_deep").paint(
                p, chev.adjusted(3, 3, -3, -3))
            right_edge = chev.left() - 4
        elif live:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.coral))
            d = 8
            p.drawEllipse(x, r.top() + (bfm.height() - d) // 2, d, d)
            x += d + 7
        # Line 1: title
        title = linked[0].title if linked is not None else rec.meta.title
        p.setFont(bold)
        p.setPen(QColor(t.on_deep))
        title_rect = QRect(x, r.top(), right_edge - x, bfm.height())
        p.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   bfm.elidedText(title, Qt.TextElideMode.ElideRight, title_rect.width()))
        # Line 2: date · duration      status (a set: its first part's date · "3 parts · 6:12")
        y2 = r.top() + bfm.height() + 3
        p.setFont(option.font)
        if linked is not None:
            st_set, parts = linked
            left = f"{fmt_date(parts[0].meta.created)}  ·  {sets.summary(st_set, parts)}"
        else:
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
        # Line 3, in a speaker search: what they said around the words.
        snippet = index.data(ROLE_SNIPPET)
        if snippet:
            y3 = y2 + fm.height() + 3
            p.setFont(option.font)
            p.setPen(QColor(t.foam))
            p.drawText(QRect(r.left(), y3, r.width(), fm.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(" ".join(snippet.split()), Qt.TextElideMode.ElideRight, r.width()))
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
