"""Recording from outside the window: system-wide shortcuts, quick notes and the recording dock."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .. import APP_NAME, export, settings
from ..library import READY, TRANSCRIPT, Recording
from . import motion
from .common import run_task
from .dialogs import ExportLibraryDialog


class CaptureMixin:
    """MainWindow's portal shortcuts (Ctrl+Alt+R, Ctrl+Alt+N), quick notes copied when ready, and the
    dock that replaces the window while recording."""

    # ---- system-wide shortcuts and quick notes ----
    def _start_global_shortcuts(self):
        import os

        if os.environ.get("ECHO_NO_PORTAL") or QApplication.platformName() == "offscreen":
            return
        if not settings.load()[0].global_shortcuts or self.shortcuts is not None:
            return
        from .shortcuts import GlobalShortcuts

        self.shortcuts = GlobalShortcuts(self)
        self.shortcuts.activated.connect(self._global_shortcut)
        self.shortcuts.start()

    def _global_shortcut(self, sid: str):
        panel = self.recorder_panel
        if sid == "record-toggle":
            panel.toggle_record()
        elif sid == "quick-note":
            if panel.session is not None:
                panel.stop()
            else:
                panel.start(quick_note=True)
                self.tray.show()
                self.tray.showMessage(APP_NAME, "Recording a quick note. Press the same keys to stop.",
                                      QSystemTrayIcon.MessageIcon.Information, 3000)

    @staticmethod
    def _transcript_time(rec: Recording) -> float | None:
        try:
            return rec.path(TRANSCRIPT).stat().st_mtime
        except OSError:
            return None

    def _shown_changed(self, ids: list):
        """Views follow the shown recording's or set's files as the transcript does."""
        rec, linked = self.current(), self.current_set()
        shown = {rec.id} if rec is not None else {r.id for r in linked[1]} if linked is not None else set()
        if shown & set(ids):
            self.views.show_subject(self.library.get(rec.id) if rec is not None else None, linked)

    def _check_transcribed(self, ids: list):
        for rid in ids:
            rec = self.library.get(rid)
            if rec is None:
                continue
            t = self._transcript_time(rec)
            if t is not None and t != self._transcript_times.get(rid):
                self._transcript_times[rid] = t
                self.transcribed.emit(rid)

    def _deliver_quick_notes(self, ids: list):
        """A quick note's text goes to the clipboard once, as soon as it is transcribed."""
        from ..library import T_DONE

        for rid in ids:
            rec = self.library.get(rid)
            if rec is None or not rec.meta.quick_note or rec.transcript_status() != T_DONE:
                continue
            text = rec.text().strip()
            rec.update(quick_note=False)
            if not text:
                continue
            QApplication.clipboard().setText(text + "\n")
            self.tray.show()
            self.tray.showMessage(APP_NAME, f"Note ready and copied to the clipboard: {text[:80]}",
                                  QSystemTrayIcon.MessageIcon.Information, 5000)
            self.show_message("Quick note copied to the clipboard.")
            QTimer.singleShot(5500, lambda: self.tray.setVisible(self.recorder_panel.session is not None
                                                                 or not self.isVisible()))

    def export_library(self):
        rec = self.current()
        dlg = ExportLibraryDialog(rec is not None, self)
        if not dlg.exec():
            return
        cfg, _ = settings.load()
        recs = [rec] if dlg.which.currentData() == "selected" and rec else \
            [r for r in self.library.all() if r.meta.state == READY]
        dest = Path(cfg.export_dir)

        def done(counts):
            self.show_message(f"Exported to {dest}: {counts['written']} written, {counts['unchanged']} up to date.")

        run_task(export.export_folder, recs, dest, cfg.export_timestamps, cfg.export_audio, on_done=done,
                 on_error=lambda m: self.show_message(f"Export failed: {m}"))

    def _notes_changed(self, ids: list):
        """With sync on, a changed recording's note is rewritten a moment later."""
        cfg, _ = settings.load()
        if cfg.export_sync and cfg.export_dir:
            self._sync_ids.update(ids)
            self._sync_timer.start()

    def _sync_notes(self):
        cfg, _ = settings.load()
        recs = [r for r in (self.library.get(i) for i in self._sync_ids) if r is not None and r.meta.state == READY]
        self._sync_ids.clear()
        if not (cfg.export_sync and cfg.export_dir and recs):
            return
        run_task(export.export_folder, recs, Path(cfg.export_dir), cfg.export_timestamps, cfg.export_audio,
                 on_error=lambda m: self.show_message(f"Keeping the notes folder up to date failed: {m}"))

    def _watched_import(self, res):
        from .. import watch

        self.model.refresh()
        self.show_message(watch.summary(res))
        ids = [r.recording.id for r in res.imported if r.recording is not None]
        if ids:
            self._look_for_bursts(ids)

    # ---- the recording dock ----
    def toggle_dock(self):
        """Swap the window for the dock, or the dock for the window (Ctrl+Shift+D)."""
        if self.dock.isVisible():
            self._from_dock("")
        else:
            self.show_dock()
            self.hide()

    def show_dock(self):
        pos = self.state.get("dock_pos")
        if not self.dock.isVisible():
            self.dock.show()
            self.dock.adjustSize()
            if isinstance(pos, list) and len(pos) == 2:
                self.dock.move(*pos)  # honored where the platform lets a window place itself (X11)
            else:
                screen = self.screen().availableGeometry()
                self.dock.move(screen.center().x() - self.dock.width() // 2, screen.top() + 24)
            motion.fade(self.dock, 1.0, motion.MEDIUM, start=0.0)
        self.dock.raise_()

    def _from_dock(self, rid: str):
        p = self.dock.pos()
        self.state.set("dock_pos", [p.x(), p.y()])
        self.dock.hide()
        self.show_window()
        if rid:
            self._select(rid)

    def _dock_shown(self, shown: bool):
        motion.clock().set_shown(shown or (self.isVisible() and not self.isMinimized()))

    def _crop_saved(self, rid: str):
        rec = self.library.get(rid)
        if rec and rec.transcript():
            self.show_message("Crop saved. Transcribe again to update the transcript for the new span.")

    def _seek_and_play(self, sec: float):
        self.player.seek(sec)
        if not self.player.is_playing():
            self.player.toggle_play()
