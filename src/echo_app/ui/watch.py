"""Watched folders in the window: a file-system watcher, a debounce, and a periodic safety scan."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from .. import settings, watch
from ..library import Library
from .common import run_task

log = logging.getLogger(__name__)

DEBOUNCE_MS = 2000  # after a change in a folder, wait for the burst of events to end
RESCAN_MS = 5 * 60 * 1000  # a full look every five minutes, in case an event was missed


class FolderWatcher(QObject):
    imported = Signal(object)  # watch.ScanResult with something imported or failed

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.scanner = watch.Scanner(library)
        self.folders: list[Path] = []
        self._fs = QFileSystemWatcher(self)
        self._fs.directoryChanged.connect(lambda _p: self._debounce.start())
        self._debounce = QTimer(self, singleShot=True, interval=DEBOUNCE_MS, timeout=self.scan)
        self._rescan = QTimer(self, interval=RESCAN_MS, timeout=self.scan)
        self._settle = QTimer(self, singleShot=True, interval=int(watch.STABLE_SECONDS * 1000) + 500,
                              timeout=self.scan)
        self._busy = False
        self._again = False

    def configure(self, folders=None):
        """Watch the folders from settings (or the ones given), and look at them now."""
        if folders is None:
            folders = settings.load()[0].watch_dirs
        self.folders = [Path(f).expanduser() for f in folders if f]
        if self._fs.directories():
            self._fs.removePaths(self._fs.directories())
        existing = [str(f) for f in self.folders if f.is_dir()]
        if existing:
            self._fs.addPaths(existing)
        if self.folders:
            self._rescan.start()
            self.scan()
        else:
            self._rescan.stop()

    def scan(self):
        if not self.folders:
            return
        if self._busy:
            self._again = True  # one more look when the running one ends
            return
        self._busy = True
        folders = list(self.folders)
        run_task(self.scanner.scan, folders, on_done=self._done, on_error=self._failed)

    def _done(self, res: watch.ScanResult):
        self._busy = False
        if res.imported or res.failed:
            self.imported.emit(res)
        if res.waiting:
            self._settle.start()  # files still being written: look again once they could have settled
        if self._again:
            self._again = False
            self.scan()

    def _failed(self, msg: str):
        self._busy = False
        log.warning("watched folders: %s", msg)

    def stop(self):
        for t in (self._debounce, self._rescan, self._settle):
            t.stop()
