"""The library list's actions: linking, sets, the selection, deleting, offers to link a burst."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from .. import APP_NAME, export, features, sets, transcription
from ..library import READY, RECORDING, T_QUEUED, T_RUNNING, Recording
from . import theme
from .common import icon, run_task
from .library_view import ROW_PART, ROW_SET
from .window_parts import _esc

log = logging.getLogger(__name__)


class LibraryActionsMixin:
    """MainWindow's actions on the list: the context menu, linking and unlinking, moving parts,
    drops, deleting, and the banner that offers to link voice notes that came in one burst."""

    # ---- linked sets in the list ----
    def eventFilter(self, obj, event):
        if obj is self.list.viewport() and event.type() == QEvent.Type.MouseButtonPress \
                and event.button() == Qt.MouseButton.LeftButton:
            idx = self.list.indexAt(event.position().toPoint())
            if idx.isValid() and self.model.kind(idx.row()) == ROW_SET \
                    and self.delegate.chevron_rect(self.list.visualRect(idx)).contains(event.position().toPoint()):
                self._toggle_expanded(self.model.row_id(idx.row()))
                return True
        if obj is self.list.viewport() and event.type() == QEvent.Type.MouseButtonDblClick:
            idx = self.list.indexAt(event.position().toPoint())
            if idx.isValid() and self.model.kind(idx.row()) == ROW_SET:
                self._toggle_expanded(self.model.row_id(idx.row()))
                return True
        if obj is self.list and event.type() == QEvent.Type.KeyPress and not event.modifiers():
            idx = self.list.currentIndex()
            kind = self.model.kind(idx.row()) if idx.isValid() else None
            if event.key() == Qt.Key.Key_Right and kind == ROW_SET:
                self.model.set_expanded(self.model.row_id(idx.row()), True)
                return True
            if event.key() == Qt.Key.Key_Left and kind == ROW_SET:
                self.model.set_expanded(self.model.row_id(idx.row()), False)
                return True
            if event.key() == Qt.Key.Key_Left and kind == ROW_PART:
                self._select(self.model.set_of(self.current().id))
                return True
        return super().eventFilter(obj, event)

    def _toggle_expanded(self, sid: str):
        self.model.set_expanded(sid, not self.model.is_expanded(sid))

    def _rename_set(self, sid: str, title: str):
        sets.rename(self.library, sid, title)
        self.model.reload_sets()

    def _show_part(self, rid: str):
        """A part heading clicked in a set's transcript: show that recording, under its open set."""
        sid = self.model.set_of(rid)
        if sid:
            self.model.set_expanded(sid, True)
        self._select(rid)

    # ---- actions on the selection ----
    def _context_menu(self, pos):
        idx = self.list.indexAt(pos)
        if not idx.isValid():
            return
        if len(self._selected_keys()) > 1 and self.list.selectionModel().isSelected(idx):
            m = QMenu(self)
            m.addAction(icon("link"), f"Link {len(self._selected_keys())} recordings", self.link_selected)
            m.addSeparator()
            m.addAction(icon("delete"), "Delete…", self.delete_selected)
            m.exec(self.list.viewport().mapToGlobal(pos))
            return
        self.list.setCurrentIndex(idx)
        linked = self.model.linked_set(idx.row())
        if linked is not None:
            st = linked[0]
            m = QMenu(self)
            m.addAction(icon("play"), "Play", self.player.toggle_play)
            m.addAction(icon("rename"), "Rename", self.player.focus_title)
            m.addAction(icon("collapse" if self.model.is_expanded(st.id) else "expand"),
                        "Hide parts" if self.model.is_expanded(st.id) else "Show parts",
                        lambda: self._toggle_expanded(st.id))
            m.addAction(icon("copy"), "Copy transcript", self.transcript.copy_all)
            m.addAction(icon("export"), "Export transcript…", self.transcript.export_text)
            m.addSeparator()
            m.addAction(icon("unlink"), "Unlink", lambda: self.unlink_set(st.id))
            m.addAction(icon("delete"), "Delete…", self.delete_selected)
            m.exec(self.list.viewport().mapToGlobal(pos))
            return
        rec = self.model.recording(idx.row())
        if rec is None:
            return
        m = QMenu(self)
        if self.model.set_of(rec.id):
            m.addAction(icon("unlink"), "Remove from set", lambda: self.remove_from_set(rec.id))
            m.addSeparator()
        ready = rec.meta.state == READY
        if ready:
            m.addAction(icon("play"), "Play", self.player.toggle_play)
        m.addAction(icon("rename"), "Rename", self.player.focus_title)
        if ready and features.transcription_installed():
            st = rec.transcript_status()
            if st in (T_RUNNING, T_QUEUED):
                m.addAction(icon("cancel"), "Cancel transcription", self.transcript.cancel)
            else:
                m.addAction(icon("transcribe"), "Transcribe again" if rec.transcript() else "Transcribe",
                            lambda: self.transcript.request(None))
        if self.transcript.has_text():
            m.addAction(icon("copy"), "Copy transcript", self.transcript.copy_all)
            m.addAction(icon("export"), "Export transcript…", self.transcript.export_text)
        if ready:
            m.addAction(icon("export"), "Export audio…", self.export_audio)
        m.addAction(icon("folder"), "Show in folder", self.show_in_folder)
        m.addSeparator()
        d = m.addAction(icon("delete"), "Delete…", self.delete_selected)
        d.setEnabled(rec.meta.state != RECORDING)
        m.exec(self.list.viewport().mapToGlobal(pos))

    def _selected_keys(self) -> list[str]:
        rows = sorted(i.row() for i in self.list.selectionModel().selectedRows())
        return [k for k in (self.model.row_id(r) for r in rows) if k and self.model.kind(self.model.row_of(k))
                in ("rec", ROW_SET, ROW_PART)]

    def _update_selection_bar(self):
        n = len(self._selected_keys())
        self.selection_bar.setVisible(n > 1)
        self.selection_label.setText(f"{n} selected")
        self.a_link.setEnabled(n > 1)

    def link_selected(self):
        keys = self._selected_keys()
        if len(keys) < 2:
            self.show_message("Select two or more recordings to link (Ctrl+click or Shift+click).")
            return
        try:
            st = sets.link(self.library, keys)
        except (KeyError, ValueError, OSError) as e:
            self.show_message(f"Could not link them: {e}")
            return
        self.model.reload_sets()
        self._select(st.id)
        self.show_message(f"Linked {len(st.members)} recordings. Drag a part to reorder it, or out to unlink it.")

    def unlink_set(self, sid: str):
        st = self.model.get_set(sid)
        parts = self.model.parts_of(sid)
        sets.dissolve(self.library, sid)
        self.model.reload_sets()
        if parts:
            self._select(parts[0].id)
        if st is not None:
            self.show_message(f"Unlinked “{st.title}”: its {len(parts)} recordings are listed on their own again.")

    def remove_from_set(self, rid: str):
        sets.unlink(self.library, rid)
        self.model.reload_sets()
        self._select(rid)

    def move_part(self, direction: int):
        rec = self.current()
        sid = self.model.set_of(rec.id) if rec else None
        if sid is None:
            return
        members = [r.id for r in self.model.parts_of(sid)]
        k = members.index(rec.id)
        if not 0 <= k + direction < len(members):
            return
        full = self.model.get_set(sid).members  # with missing members, which keep their places
        target = full.index(members[k + direction])
        sets.move(self.library, sid, rec.id, target)
        self.model.reload_sets()
        self._select(rec.id)

    def _dropped(self, ids: list, target: str | None, sid: str | None, before: str | None):
        """A drag in the list: onto a row (target) links, between parts (into set `sid`, before the
        part `before`) places, between top-level rows takes parts out of their set."""
        try:
            if target is not None:
                tsid = self.model.set_of(target) or (target if sets.is_set_id(target) else None)
                ids = [i for i in ids if i != target and i != tsid]
                if not ids:
                    return
                st = sets.link(self.library, [tsid or target, *ids])
                if tsid and not sets.is_set_id(target):
                    # Dropped on a part: the new ones go right after it, in the order dragged.
                    for n, rid in enumerate(i for i in ids if not sets.is_set_id(i)):
                        st = sets.move(self.library, st.id, rid, st.members.index(target) + 1 + n)
                select = st.id
            elif sid is not None:
                moving = [i for i in ids if not sets.is_set_id(i) and i != before]
                if not moving:
                    return
                for rid in moving:
                    st = sets.get(self.library, sid)
                    rest = [m for m in st.members if m != rid]
                    sets.move(self.library, sid, rid, rest.index(before) if before in rest else len(rest))
                select = moving[0]
            else:
                for rid in ids:
                    if not sets.is_set_id(rid) and self.model.set_of(rid):
                        sets.unlink(self.library, rid)
                select = ids[0]
        except (KeyError, ValueError, OSError) as e:
            self.show_message(f"Could not link them: {e}")
            return
        self.model.reload_sets()
        self._select(select)

    def delete_selected(self):
        # What is highlighted, not the current row: Ctrl+click can unselect the current row.
        keys = self._selected_keys()
        if len(keys) > 1:
            self._delete_many(keys)
            return
        if not keys:
            return
        row = self.model.row_of(keys[0])
        linked = self.model.linked_set(row)
        if linked is not None:
            self._delete_set(*linked)
            return
        rec = self.model.recording(row)
        if rec is None or rec.meta.state == RECORDING:
            return
        r = QMessageBox.question(self, "Delete recording",
                                 f"Move “{rec.meta.title}” and its transcript to the trash?\n"
                                 "You can restore it from the trash.")
        if r != QMessageBox.StandardButton.Yes:
            return
        self._trash([rec])

    def _delete_set(self, st, parts):
        box = QMessageBox(QMessageBox.Icon.Question, "Delete linked set",
                          f"“{st.title}” links {len(parts)} recordings.", parent=self)
        box.setInformativeText("Unlink them to keep each recording, or move all of them and their "
                               "transcripts to the trash.")
        unlink = box.addButton("Unlink", QMessageBox.ButtonRole.AcceptRole)
        trash = box.addButton(f"Move {len(parts)} to the trash", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(unlink)
        box.exec()
        if box.clickedButton() is unlink:
            self.unlink_set(st.id)
        elif box.clickedButton() is trash:
            self._trash([r for r in parts if r.meta.state != RECORDING])
            sets.dissolve(self.library, st.id)
            self.model.reload_sets()

    def _delete_many(self, keys: list[str]):
        recs: dict[str, Recording] = {}
        for k in keys:
            if sets.is_set_id(k):
                recs.update({r.id: r for r in self.model.parts_of(k)})
            else:
                r = self.library.get(k)
                if r is not None:
                    recs[r.id] = r
        recs = {i: r for i, r in recs.items() if r.meta.state != RECORDING}
        if not recs:
            return
        r = QMessageBox.question(self, "Delete recordings",
                                 f"Move {len(recs)} recordings and their transcripts to the trash?\n"
                                 "You can restore them from the trash.")
        if r == QMessageBox.StandardButton.Yes:
            self._trash(list(recs.values()))

    def _trash(self, recs: list[Recording]):
        row = self.list.currentIndex().row()
        shown = {self.player.rec.id} if self.player.rec else set()
        shown |= {p.rec.id for p in self.player.parts}
        if shown & {r.id for r in recs}:
            self.transcript.save()  # edits in other parts of a shown set are kept
            self.player.set_recording(None)
            self.transcript.set_recording(None)
        done = 0
        for rec in recs:
            transcription.cancel(rec)
            try:
                self.library.delete(rec)
                done += 1
            except OSError as e:
                self.show_message(f"Could not delete “{rec.meta.title}”: {e}")
        self.model.refresh()
        nearest = self.model.nearest_row(min(row, self.model.rowCount() - 1))
        if nearest >= 0:
            self.list.setCurrentIndex(self.model.index(nearest))
        self._last_selected = None
        if done == 1 and len(recs) == 1:
            self.show_message(f"Moved “{recs[0].meta.title}” to the trash.")
        elif done:
            self.show_message(f"Moved {done} recordings to the trash.")

    def show_in_folder(self):
        rec = self.current()
        if rec:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(rec.folder)))

    def export_audio(self):
        rec = self.current()
        if rec is None or rec.meta.state != READY:
            return
        cropped = rec.meta.crop_start or rec.meta.crop_end is not None
        ext = ".flac" if cropped else (rec.audio_path.suffix if rec.audio_path else ".flac")
        start = str(Path.home() / export.suggested_name(rec, ext))
        path, _ = QFileDialog.getSaveFileName(self, "Export audio", start, f"Audio (*{ext})")
        if not path:
            return

        def done(out):
            self.show_message(f"Saved {out}")

        run_task(export.export_audio, rec, Path(path), on_done=done,
                 on_error=lambda m: self.show_message(f"Export failed: {m}"))

    # ---- offers to link a burst ----
    def _look_for_bursts(self, ids: list[str]):
        run_task(sets.bursts, self.library, ids, on_done=self._got_offers,
                 on_error=lambda m: log.warning("looking for bursts failed: %s", m))

    def _got_offers(self, offers):
        dismissed = set(self.state.get("dismissed_offers") or [])
        known = {o.key for o in self._offers}
        self._offers += [o for o in offers if o.key not in dismissed and o.key not in known]
        self._show_offer()

    def _show_offer(self):
        if not self._offers:
            self.banner.hide()
            return
        o = self._offers[0]
        first = self.library.get(o.ids[0])
        day = ""
        if first is not None:
            from datetime import datetime

            try:
                day = f" from {datetime.fromisoformat(first.meta.created).strftime('%-d %b')}"
            except ValueError:
                pass
        n = len(o.ids)
        what = f"{n} voice notes{day}" if n > 1 else f"This voice note{day}"
        a = f"<a href='#' style='color: {theme.current().foam}; font-weight: 700; text-decoration: none;'>"
        if o.set_id:
            text = f"{a}{what}</a> seem{'s' if n == 1 else ''} to continue “{_esc(o.set_title)}”."
            self.banner_link.setText("Add to set")
        else:
            text = f"{a}{what}</a> look like one conversation."
            self.banner_link.setText("Link them")
        if len(self._offers) > 1:
            text += f" <span>(1 of {len(self._offers)})</span>"
        self.banner_text.setText(text)
        self.banner_text.setToolTip("Click to select them in the list")
        self.banner.show()

    def _select_offer(self):
        if not self._offers:
            return
        sm = self.list.selectionModel()
        rows = [self.model.row_of(i) for i in self._offers[0].ids]
        rows = [r for r in rows if r >= 0]
        if not rows:
            return
        self.list.setCurrentIndex(self.model.index(rows[0]))
        for r in rows[1:]:
            sm.select(self.model.index(r), QItemSelectionModel.SelectionFlag.Select)

    def _accept_offer(self):
        if not self._offers:
            return
        o = self._offers.pop(0)
        ids = [i for i in o.ids if self.library.get(i) is not None]
        try:
            st = sets.link(self.library, [o.set_id, *ids] if o.set_id else ids)
        except (KeyError, ValueError, OSError) as e:
            self.show_message(f"Could not link them: {e}")
        else:
            self.model.reload_sets()
            self._select(st.id)
            self.show_message(f"Linked into “{st.title}”.")
        self._show_offer()

    def _dismiss_offer(self):
        if not self._offers:
            return
        o = self._offers.pop(0)
        self.state.set("dismissed_offers", [*(self.state.get("dismissed_offers") or []), o.key][-200:])
        self._show_offer()

    def _meta_changed(self, rid: str):
        self.model.reload(rid)
        self._update_tags()

    def _tray_mark(self):
        """From the tray the window may be hidden: mark without opening the note field."""
        if self.recorder_panel.mark_quietly():
            self.tray.showMessage(APP_NAME, "Marker added.", QSystemTrayIcon.MessageIcon.Information, 2000)
