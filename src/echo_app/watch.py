"""Watched folders: import new audio files that appear in them (stdlib only).

The scanner is shared by the window (woken by a file-system watcher) and `echo-app import
--watch` (which polls). A file is imported once its size has stayed the same for a few seconds,
so a phone sync or a copy still in progress is left alone. Originals stay where they are.

The ledger, ``<data>/watch.json``, remembers per folder which files were already handled (by
size and modification time, so unchanged files are not hashed again) and which failed and why;
a failed file is tried again only when it changes.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import importer
from .fsutil import atomic_write_json, read_json
from .library import Library

log = logging.getLogger(__name__)

STABLE_SECONDS = 3.0
LEDGER = "watch.json"


@dataclass
class ScanResult:
    imported: list[importer.Result] = field(default_factory=list)
    duplicates: int = 0
    failed: list[importer.Result] = field(default_factory=list)
    waiting: int = 0  # files still changing; scan again in a few seconds


def _signature(st: os.stat_result) -> list[int]:
    return [st.st_size, st.st_mtime_ns]


def _can_open(path: Path) -> bool:
    """On Windows a file still being written cannot be opened for writing by another process.
    POSIX has no such lock (and synced folders may be read-only), so there it is not checked."""
    if os.name != "nt":
        return True
    try:
        with open(path, "ab"):
            return True
    except OSError:
        return False


class Scanner:
    def __init__(self, lib: Library, stable_seconds: float = STABLE_SECONDS):
        self.lib = lib
        self.stable_seconds = stable_seconds
        self._seen_changing: dict[str, tuple[list[int], float]] = {}  # path -> (signature, first seen)

    @property
    def ledger_path(self) -> Path:
        return self.lib.data_dir / LEDGER

    def _ledger(self) -> dict:
        try:
            data = read_json(self.ledger_path)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def candidates(self, folder: Path) -> list[Path]:
        try:
            entries = list(os.scandir(folder))
        except OSError as e:
            log.warning("cannot read watched folder %s: %s", folder, e)
            return []
        return sorted(Path(e.path) for e in entries
                      if e.is_file() and not e.name.startswith(".")
                      and Path(e.name).suffix.lower() in importer.EXTENSIONS)

    def scan(self, folders, auto_transcribe: bool | None = None) -> ScanResult:
        """Import every new, settled audio file in `folders` (not their subfolders)."""
        res = ScanResult()
        ledger = self._ledger()
        changed = False
        now = time.monotonic()
        hashes = None
        ready: list[tuple[str, Path, list[int]]] = []
        for folder in folders:
            folder = Path(folder).expanduser()
            book = ledger.setdefault(str(folder), {"handled": {}, "failed": {}})
            for path in self.candidates(folder):
                try:
                    sig = _signature(path.stat())
                except OSError:
                    continue
                key = str(path)
                if book["handled"].get(key) == sig:
                    continue
                failed = book["failed"].get(key)
                if failed and failed.get("signature") == sig:
                    continue  # reported once; tried again only when the file changes
                first = self._seen_changing.get(key)
                if first is None or first[0] != sig:
                    self._seen_changing[key] = (sig, now)
                    res.waiting += 1
                    continue
                if now - first[1] < self.stable_seconds or not _can_open(path):
                    res.waiting += 1
                    continue
                ready.append((str(folder), path, sig))
        for folder_key, path, sig in ready:
            book = ledger[folder_key]
            if hashes is None:
                hashes = importer.library_hashes(self.lib)
            r = importer.import_file(self.lib, path, hashes)
            self._seen_changing.pop(str(path), None)
            changed = True
            if r.status == importer.REJECTED:
                book["failed"][str(path)] = {"signature": sig, "reason": r.message}
                res.failed.append(r)
                log.info("watched %s: not imported: %s", path, r.message)
                continue
            book["handled"][str(path)] = sig
            book["failed"].pop(str(path), None)
            if r.status == importer.DUPLICATE:
                res.duplicates += 1
            else:
                res.imported.append(r)
                log.info("watched %s: imported as %s", path, r.recording.id)
        if res.imported:
            if auto_transcribe is None:
                from . import features

                auto_transcribe = features.auto_transcribe()
            if auto_transcribe:
                from . import transcription

                for r in res.imported:
                    transcription.request(self.lib, r.recording, start_worker=False)
                transcription.ensure_worker(self.lib)
        if changed:
            try:
                atomic_write_json(self.ledger_path, ledger)
            except OSError as e:
                log.warning("could not save the watch ledger: %s", e)
        return res


def summary(res: ScanResult) -> str:
    """"Imported 2 new files from watched folders (1 could not be imported)." or ""."""
    if not res.imported and not res.failed:
        return ""
    parts = []
    if res.imported:
        n = len(res.imported)
        parts.append(f"Imported {n} new file{'s' if n != 1 else ''} from watched folders")
    if res.failed:
        names = ", ".join(r.source.name for r in res.failed[:3])
        parts.append(f"could not import {names}" + ("…" if len(res.failed) > 3 else ""))
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def watch_forever(lib: Library, folders, interval: float = 30.0, out=print) -> None:
    """`echo-app import --watch`: poll the folders until interrupted."""
    scanner = Scanner(lib)
    for f in folders:
        out(f"Watching {f}")
    while True:
        res = scanner.scan(folders)
        for r in res.imported:
            out(f"+ {r.source.name}: {r.message}")
        for r in res.failed:
            out(f"! {r.source.name}: {r.message}")
        # Files still settling are looked at again soon rather than after the full interval.
        time.sleep(min(interval, scanner.stable_seconds + 0.5) if res.waiting else interval)
