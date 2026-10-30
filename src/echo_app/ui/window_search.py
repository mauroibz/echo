"""Searching the library and importing into it."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from .. import importer
from ..index import Index, parse_people, parse_query
from .common import run_task


class SearchImportMixin:
    """MainWindow's search box (with @people), and importing files from a dialog, a drop or a
    watched folder."""

    # ---- search ----
    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _search_words(self) -> str:
        return " ".join(parse_query(self.search.text())[0])

    def _offer_people(self, text: str):
        token = text[:self.search.cursorPosition()].split(" ")[-1]
        if not token.startswith("@"):
            self._people.popup().hide()
            return
        idx = Index(self.library)
        try:
            idx.sync()  # only folders changed since the last search are read again
            names = [n.replace(" ", "_") for n, _count in idx.speakers()]
        finally:
            idx.close()
        self._people.model().setStringList(names)
        self._people.setCompletionPrefix(token[1:])
        if self._people.completionCount():
            self._people.complete()
        else:
            self._people.popup().hide()

    def _complete_person(self, name: str):
        text, pos = self.search.text(), self.search.cursorPosition()
        start = text.rfind(" ", 0, pos) + 1
        self.search.setText(f"{text[:start]}@{name} {text[pos:].lstrip()}")
        self.search.setCursorPosition(start + len(name) + 2)

    def _carry_search(self):
        """Open a search result with its words already found in the transcript, so finding
        them there takes no second search; in a speaker search, only in their passages."""
        words = self._search_words()
        rec = self.current()
        numbers = None
        if rec is not None and parse_people(self.search.text()):
            numbers = (self._speech.get(rec.id) or {}).get("numbers")
        if words and (rec is not None or self.current_set() is not None):
            self.transcript.find_from_search(words, numbers)

    def _run_search(self):
        q = self.search.text().strip()
        if not self._search_words():
            self.transcript.search_cleared()
        if not q:
            self.model.set_filter(None)
            self._update_empty()
            return
        lib = self.library

        def query():
            idx = Index(lib)
            try:
                idx.sync()
                return {r["id"] for r in idx.list(q)}, idx.speech_matches(q) if parse_people(q) else {}
            finally:
                idx.close()

        def done(result):
            ids, speech = result
            if self.search.text().strip() == q:
                self._speech = speech
                self.model.set_filter(ids, {rid: m["snippet"] for rid, m in speech.items() if m["snippet"]})
                self._update_empty()
                if self.model.first_row() >= 0 and not self.list.currentIndex().isValid():
                    self.list.setCurrentIndex(self.model.index(self.model.first_row()))
                # Also when the open recording stays selected through the filter (no selection change).
                linked = self.current_set()
                if (self.current() is not None and self.current().id in ids) or \
                        (linked is not None and any(r.id in ids for r in linked[1])):
                    self._carry_search()

        run_task(query, on_done=done, on_error=lambda m: self.show_message(f"Search failed: {m}"))

    # ---- import ----
    def import_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import audio or video", str(Path.home()),
            "Audio and video (" + " ".join(f"*{e}" for e in sorted(importer.EXTENSIONS)) + ");;All files (*)")
        if paths:
            self.import_paths([Path(p) for p in paths])

    def import_paths(self, paths: list[Path]):
        if not paths:
            return
        lib = self.library
        self.show_message("Importing…")

        def progress(i, n, path, emit=None):
            pass

        def work(progress):
            return importer.import_paths(
                lib, paths, progress=lambda i, n, p, frac=None: progress((i, n, p.name, frac)))

        def on_progress(v):
            i, n, name, frac = v
            if name:
                # A long video whose sound is converted rather than copied takes a while: show how far.
                pct = f" ({frac:.0%})" if frac is not None else ""
                self.show_message(f"Importing {i + 1} of {n}: {name}{pct}", 10_000)

        def done(results):
            imported = [r for r in results if r.status == importer.IMPORTED]
            dups = [r for r in results if r.status == importer.DUPLICATE]
            bad = [r for r in results if r.status == importer.REJECTED]
            self.model.refresh()
            if imported:
                self._select(imported[0].recording.id)
                self._look_for_bursts([r.recording.id for r in imported])
            parts = []
            if imported:
                parts.append(f"Imported {len(imported)}")
            if dups:
                parts.append(f"{len(dups)} already in the library")
            if bad:
                parts.append(f"{len(bad)} not imported")
            self.show_message(", ".join(parts) + "." if parts else "No audio or video files found.")
            if bad or (dups and not imported):
                lines = [f"• {r.source.name}: {r.message}" for r in bad + dups]
                box = QMessageBox(QMessageBox.Icon.Information if not bad else QMessageBox.Icon.Warning,
                                  "Import", ", ".join(parts) + ".", parent=self)
                box.setDetailedText("\n".join(lines))
                box.setInformativeText("\n".join(lines[:6]) + ("\n…" if len(lines) > 6 else ""))
                box.exec()

        run_task(work, on_done=done, on_progress=on_progress,
                 on_error=lambda m: self.show_message(f"Import failed: {m}"))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.overlay.setGeometry(self.centralWidget().geometry().adjusted(12, 12, -12, -12))
            self.overlay.show()
            self.overlay.raise_()

    def dragLeaveEvent(self, e):
        self.overlay.hide()

    def dropEvent(self, e):
        self.overlay.hide()
        urls = e.mimeData().urls()
        local = [Path(u.toLocalFile()) for u in urls if u.isLocalFile()]
        remote = [u for u in urls if not u.isLocalFile()]
        if remote:
            self.show_message("Only files on this computer can be imported; save web audio first.")
        if local:
            e.acceptProposedAction()
            self.import_paths(local)
