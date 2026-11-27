"""Collections in the window: opening one, filing recordings, and asking where a dropped batch goes."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox

from .. import bundle, collections, importer
from .collections import CollectionDialog
from .common import icon

ASK_FROM = 2  # files coming in at once before Echo asks about a collection: one file is the day to day


class CollectionsMixin:
    """MainWindow's collections: the bar above the list, the list's scope, Move to collection, a
    collection's own menu (bundle, rename, dissolve), and the question on a batch import."""

    def open_collection(self, name: str | None):
        """Show a collection's recordings in the list, or with None the day-to-day ones."""
        if self.search.text():
            self.search.clear()  # a search looks everywhere: opening a place ends it
            self.model.set_filter(None)
        self.model.set_collection(name)
        self.collection_bar.set_open(self.model.collection())
        self.list.setAccessibleName(self.model.collection() or "Recordings")
        self._update_empty()
        if not self.list.currentIndex().isValid() and self.model.first_row() >= 0:
            self.list.setCurrentIndex(self.model.index(self.model.first_row()))

    def _update_collections(self):
        """Called with every refresh: the bar's rows and counts, and back to the day to day when
        the open collection lost its last recording."""
        items = self.model.collections()
        self.collection_bar.set_items(self.model.daily(), items)
        if self.model._collection and self.model.collection() is None:
            self.open_collection(None)

    def _scope_to(self, key: str):
        """Before selecting a recording from elsewhere (a search result opened, an extension's
        page): open the place it is filed in."""
        if self.search.text():
            return  # a search shows every place at once
        # Also when its row is there: the recording being made shows everywhere, and once it stops
        # it is only where it was filed.
        where = self.model.collection_of(key)
        if where != self.model.collection():
            self.model.set_collection(where)
            self.collection_bar.set_open(self.model.collection())

    # ---- filing ----
    def _selected_recordings(self):
        try:
            return bundle.expand(self.library, self._selected_keys())
        except KeyError:
            return []

    def _collection_menu(self, menu: QMenu):
        """"Move to collection" for the selection: each collection, a new one, and out of it."""
        recs = self._selected_recordings()
        if not recs:
            return
        here = {collections.clean(r.meta.collection) for r in recs}
        m = menu.addMenu(icon("folder"), "Move to collection")
        for c in self.model.collections():
            a = m.addAction(c.name, lambda n=c.name: self.file_selected(n))
            a.setEnabled(here != {c.name})
        if self.model.collections():
            m.addSeparator()
        m.addAction("New collection…", self.file_selected_new)
        if here != {""}:
            m.addSeparator()
            m.addAction("Back to Recordings", lambda: self.file_selected(""))

    def file_selected_new(self):
        name, ok = QInputDialog.getText(self, "New collection", "Name:")
        if ok and collections.clean(name):
            self.file_selected(name)

    def file_selected(self, name: str):
        self.file_recordings(self._selected_recordings(), name)

    def file_recordings(self, recs, name: str):
        """Move recordings into a collection ("": back to the day-to-day list) and say so."""
        name = collections.spelling(self.library, name)
        n = collections.file(recs, name)
        if not n:
            return
        row = self.list.currentIndex().row()
        self.model.refresh()
        self._update_collections()
        nearest = self.model.nearest_row(min(max(row, 0), self.model.rowCount() - 1))
        if nearest >= 0 and not self.list.currentIndex().isValid():
            self.list.setCurrentIndex(self.model.index(nearest))
        what = f"“{recs[0].meta.title}”" if n == 1 and len(recs) == 1 else f"{n} recordings"
        self.show_message(f"Moved {what} to “{name}”." if name else f"Moved {what} back to Recordings.")

    def _dropped_on_collection(self, name, ids: list):
        try:
            recs = bundle.expand(self.library, ids)
        except KeyError:
            return
        self.file_recordings(recs, name or "")

    # ---- a collection's own menu ----
    def _collection_context(self, name: str, pos):
        c = collections.get(self.library, name)
        if c is None:
            return
        m = QMenu(self)
        here = collections.same(self.recorder_panel.destination(), name)
        a = m.addAction(icon("mic"), "File new recordings here", lambda: self.recorder_panel.set_destination(
            "" if here else name))
        a.setCheckable(True)
        a.setChecked(here)
        m.addSeparator()
        m.addAction(icon("share"), "Bundle…", lambda: self.bundle_collection(name))
        m.addAction(icon("rename"), "Rename…", lambda: self.rename_collection(name))
        m.addSeparator()
        m.addAction(icon("unlink"), "Move all back to Recordings…", lambda: self.dissolve_collection(name))
        m.exec(pos)

    def bundle_collection(self, name: str):
        c = collections.get(self.library, name)
        if c is not None:
            self.transcript.save()
            self.bundle_recordings(sorted(c.recordings, key=lambda r: r.meta.created), f"“{c.name}”", c.name)

    def rename_collection(self, name: str):
        new, ok = QInputDialog.getText(self, "Rename collection", "Name:", text=name)
        new = collections.clean(new)
        if not ok or not new or new == name:
            return
        was_open = self.model.collection() is not None and collections.same(self.model.collection(), name)
        collections.rename(self.library, name, new)
        if collections.same(self.recorder_panel.destination(), name):
            self.recorder_panel.set_destination(new)  # new recordings follow the collection
        self.model.refresh()
        if was_open:
            self.model.set_collection(new)
        self._update_collections()
        self.collection_bar.set_open(self.model.collection())

    def dissolve_collection(self, name: str):
        c = collections.get(self.library, name)
        if c is None:
            return
        n = len(c.recordings)
        r = QMessageBox.question(self, "Move back to Recordings",
                                 f"Move the {n} recording{'s' if n != 1 else ''} of “{c.name}” back to your "
                                 "day-to-day list?\nNothing is deleted; the collection goes away.")
        if r == QMessageBox.StandardButton.Yes:
            self.file_recordings(c.recordings, "")
            if collections.same(self.recorder_panel.destination(), name):
                self.recorder_panel.set_destination("")  # or the next recording would bring it back

    # ---- importing a batch ----
    def import_asking(self, paths: list[Path]):
        """Import files dropped or chosen: into the open collection; else, for several, into the
        collection the user names (or the day-to-day list); one file goes to the list unasked."""
        if not paths:
            return
        here = self.model.collection()
        if here is not None:
            self.import_paths(paths, here)
            return
        files = importer.expand(paths)
        if len(files) < ASK_FROM:
            self.import_paths(paths)
            return
        folders = [p for p in paths if p.is_dir()]
        dlg = CollectionDialog(len(files), [c.name for c in self.model.collections()],
                               folders[0].name if len(folders) == 1 and len(paths) == 1 else "", self)
        if dlg.exec():
            self.import_paths(paths, collections.spelling(self.library, dlg.name) if dlg.name else "")
