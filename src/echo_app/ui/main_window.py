"""The main window."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, QObject, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QFrame, QLabel, QLineEdit, QListView,
                               QMainWindow, QMenu, QMessageBox, QSplitter, QStatusBar, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from .. import APP_NAME, export, features, importer, recorder, transcription
from ..index import Index
from ..library import READY, RECORDING, T_QUEUED, T_RUNNING, Library, Recording
from . import theme
from .common import RECORD_RED, UiState, app_icon, dot_icon, fmt_duration, icon, run_task
from .dialogs import AboutDialog, DoctorDialog, ModelDialog, SettingsDialog, ShortcutsDialog, WelcomeDialog
from .library_view import LibraryModel, RowDelegate
from .player import PlayerPanel
from .recorder_panel import RecorderPanel
from .transcript import TranscriptPanel

log = logging.getLogger(__name__)


class _SpaceFilter(QObject):
    """Space toggles playback when focus is on the list or the waveform."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space and not event.modifiers():
            self.callback()
            return True
        return False


class DropOverlay(QLabel):
    def __init__(self, parent):
        super().__init__("Drop audio files to import", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(theme.display_font(1.6, QFont.Weight.ExtraBold))
        self._restyle()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def _restyle(self):
        t = theme.current()
        self.setStyleSheet(f"QLabel {{ background: {theme.rgba('deep_mid', 0.82)}; color: {t.on_deep};"
                           f" border: 2px dashed {t.foam}; border-radius: 18px; }}")

    def showEvent(self, e):
        self._restyle()
        super().showEvent(e)


class MainWindow(QMainWindow):
    def __init__(self, library: Library, state: UiState):
        super().__init__()
        self.library = library
        self.state = state
        self._told_background = False
        self._quitting = False
        self._last_selected: str | None = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self._build()
        self._build_menus()
        self._build_tray()
        self._restore()
        self._refresh_timer = QTimer(self, interval=1000, timeout=self._refresh)
        self._refresh_timer.start()
        self._search_timer = QTimer(self, singleShot=True, interval=200, timeout=self._run_search)
        self.model.refresh()
        self._select_initial()
        self._attach_active()
        QTimer.singleShot(0, self._startup_tasks)

    # ---- construction ----
    def _build(self):
        self.recorder_panel = RecorderPanel(self.library)
        self.recorder_panel.message.connect(self.show_message)
        self.recorder_panel.started.connect(self._recording_started)
        self.recorder_panel.stopped.connect(self._recording_stopped)
        self.recorder_panel.recording_changed.connect(lambda _r: self._update_title())

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search titles and transcripts")
        self.search.setAccessibleName("Search recordings")
        self.search.addAction(icon("find", "on_deep_muted"), QLineEdit.ActionPosition.LeadingPosition)
        self._clear_search = self.search.addAction(icon("close", "on_deep"), QLineEdit.ActionPosition.TrailingPosition)
        self._clear_search.setToolTip("Clear (Esc)")
        self._clear_search.triggered.connect(self.search.clear)
        self._clear_search.setVisible(False)
        self.search.textChanged.connect(lambda t: self._clear_search.setVisible(bool(t)))
        self.search.textChanged.connect(lambda _t: self._search_timer.start())

        self.model = LibraryModel(self.library, self)
        self.model.modelReset.connect(lambda: QTimer.singleShot(0, self._update_empty))
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setItemDelegate(RowDelegate(self.list))
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setUniformItemSizes(True)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setMouseTracking(True)
        self.list.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.selectionModel().currentChanged.connect(self._selection_changed)
        self.list.setAccessibleName("Recordings")
        self.empty = QLabel("No recordings yet.\n\nPress Record (Ctrl+R),\nor drop audio files here.", self.list)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        theme.set_role(self.empty, dim=True)

        left = theme.DeepBackground()
        left.setObjectName("sidebar")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        ll.addWidget(self.recorder_panel)
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(14, 2, 14, 4)
        sl.setSpacing(12)
        sl.addWidget(self.search)
        self.list_label = QLabel("RECORDINGS")
        self.list_label.setFont(theme.display_font(0.78, QFont.Weight.ExtraBold))
        theme.set_role(self.list_label, eyebrow=True)
        sl.addWidget(self.list_label)
        ll.addWidget(sw)
        ll.addWidget(self.list, 1)

        self.player = PlayerPanel()
        self.player.message.connect(self.show_message)
        self.player.renamed.connect(lambda rid, _t: self.model.reload(rid))
        self.player.crop_saved.connect(self._crop_saved)
        self.player.export_requested.connect(self.export_audio)
        self.transcript = TranscriptPanel(self.library)
        self.transcript.message.connect(self.show_message)
        self.transcript.seek_requested.connect(self._seek_and_play)
        self.transcript.download_requested.connect(self.show_model_dialog)
        self.transcript.changed.connect(self.model.reload)
        self.player.position_changed.connect(self.transcript.follow)

        for card in (self.player, self.transcript):
            card.setObjectName("card")
            card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.right_split = QSplitter(Qt.Orientation.Vertical)
        self.right_split.setObjectName("content")
        self.right_split.addWidget(self.player)
        self.right_split.addWidget(self.transcript)
        self.right_split.setStretchFactor(0, 0)
        self.right_split.setStretchFactor(1, 1)
        self.right_split.setChildrenCollapsible(False)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 14, 14, 8)
        rl.addWidget(self.right_split)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setObjectName("main")
        self.split.setHandleWidth(1)
        self.split.addWidget(left)
        self.split.addWidget(right)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setChildrenCollapsible(False)
        left.setMinimumWidth(280)
        self.setCentralWidget(self.split)

        self.setStatusBar(QStatusBar())
        self.worker_label = QLabel("")
        self.statusBar().addPermanentWidget(self.worker_label)
        self.overlay = DropOverlay(self)

        self._space = _SpaceFilter(self.player.toggle_play)
        self.list.installEventFilter(self._space)
        self.player.wave.installEventFilter(self._space)

    def _act(self, menu: QMenu, text: str, slot, shortcut=None, ic: str | None = None) -> QAction:
        a = QAction(text, self)
        if ic:
            a.setIcon(icon(ic))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        menu.addAction(a)
        self.addAction(a)
        return a

    def _build_menus(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        self._act(f, "&Import audio…", self.import_dialog, "Ctrl+O", "import")
        self.a_export_text = self._act(f, "&Export transcript…", self.transcript.export_text, "Ctrl+E", "export")
        self.a_export_audio = self._act(f, "Export &audio…", self.export_audio, None, "export")
        self.a_folder = self._act(f, "Show in &folder", self.show_in_folder, None, "folder")
        f.addSeparator()
        self._act(f, "&Settings…", self.show_settings, "Ctrl+,", "settings")
        f.addSeparator()
        self._act(f, "&Quit", self.quit, "Ctrl+Q")

        e = mb.addMenu("&Edit")
        self.a_copy = self._act(e, "&Copy transcript", self.transcript.copy_all, "Ctrl+Shift+C", "copy")
        self._act(e, "&Find in transcript…", self.transcript.open_find, "Ctrl+F", "find")
        self._act(e, "&Search recordings", self._focus_search, "Ctrl+K", "find")
        e.addSeparator()
        self.a_rename = self._act(e, "&Rename", self.player.focus_title, "F2", "rename")
        self.a_delete = self._act(e, "&Delete…", self.delete_selected, "Del", "delete")
        self.a_delete.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.list.addAction(self.a_delete)

        r = mb.addMenu("&Recording")
        self.a_record = self._act(r, "&Record", self.recorder_panel.toggle_record, "Ctrl+R")
        self.a_record.setIcon(dot_icon(RECORD_RED))
        self.a_pause = self._act(r, "&Pause / resume", self.recorder_panel.toggle_pause, "Ctrl+Shift+R", "pause")
        r.addSeparator()
        self._act(r, "Play / pause", self.player.toggle_play, "Ctrl+Space", "play")
        r.addSeparator()
        self.a_transcribe = self._act(r, "&Transcribe", lambda: self.transcript.request(None), None, "transcribe")
        self.a_cancel = self._act(r, "&Cancel transcription", self.transcript.cancel, None, "cancel")

        h = mb.addMenu("&Help")
        self._act(h, "&Keyboard shortcuts", lambda: ShortcutsDialog(self).exec(), "F1")
        self._act(h, "Transcription &model…", self.show_model_dialog, None, "download")
        self._act(h, "&Check setup…", lambda: DoctorDialog(self).exec(), None, "help")
        h.addSeparator()
        self._act(h, f"&About {APP_NAME}", lambda: AboutDialog(self.library.data_dir, self).exec())

        QShortcut(QKeySequence("Escape"), self.search, activated=self.search.clear,
                  context=Qt.ShortcutContext.WidgetShortcut)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(dot_icon(RECORD_RED, 64), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Show Echo", self.show_window)
        self.tray_stop = menu.addAction("Stop recording", self.recorder_panel.stop)
        menu.addSeparator()
        menu.addAction("Quit Echo", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window()
                                    if reason == QSystemTrayIcon.ActivationReason.Trigger else None)

    # ---- state ----
    def _restore(self):
        geo = self.state.get("geometry")
        if geo and len(geo) == 4:
            self.setGeometry(*geo)
        else:
            self.resize(1180, 760)
        if self.state.get("maximized"):
            self.setWindowState(Qt.WindowState.WindowMaximized)
        self.split.setSizes(self.state.get("split") or [330, 850])
        self.right_split.setSizes(self.state.get("right_split") or [200, 560])
        self.player.set_speed(self.state.get("speed", 1.0))

    def _save_state(self):
        if not self.isMaximized():
            g = self.geometry()
            self.state.set("geometry", [g.x(), g.y(), g.width(), g.height()])
        self.state.set("maximized", self.isMaximized())
        self.state.set("split", self.split.sizes())
        self.state.set("right_split", self.right_split.sizes())
        self.state.set("speed", self.player.speed_value())
        rec = self.current()
        if rec:
            self.state.set("selected", rec.id)
        self.state.save()

    def _select_initial(self):
        rid = self.state.get("selected")
        row = self.model.row_of(rid) if rid else -1
        if row < 0 and self.model.rowCount():
            row = 0
        if row >= 0:
            self.list.setCurrentIndex(self.model.index(row))
        self._update_empty()

    # ---- startup work ----
    def _startup_tasks(self):
        lib = self.library

        def recover():
            importer.clean_staging(lib)
            actions = recorder.recover_all(lib)
            transcription.resume_pending(lib)
            return actions

        def recovered(actions):
            n = sum(1 for _rid, a in actions if a in ("finalized", "adopted"))
            if any(a == "finalized" for _rid, a in actions):
                self.show_message(f"Recovered {n} recording{'s' if n > 1 else ''} after an interruption.")
            self._refresh()
            self._attach_active()

        run_task(recover, on_done=recovered, on_error=lambda m: self.show_message(f"Recovery problem: {m}"))

        def sync_index():
            idx = Index(lib)
            try:
                return idx.sync()
            finally:
                idx.close()

        run_task(sync_index)

    def _attach_active(self):
        if self.recorder_panel.session is None:
            sess = recorder.active(self.library)
            if sess is not None:
                self.recorder_panel.attach(sess)
                self._select(sess.rec.id)
        self._update_title()

    # ---- periodic refresh ----
    def _refresh(self):
        self.model.refresh()
        self._update_empty()
        rec = self.current()
        if rec is not None:
            fresh = self.library.get(rec.id)
            if fresh is None:
                self.player.set_recording(None)
                self.transcript.set_recording(None)
            else:
                self.player.set_recording(fresh)
                self.transcript.refresh()
        elif self.model.rowCount() and not self.list.currentIndex().isValid():
            self.list.setCurrentIndex(self.model.index(0))
        recording = [r for r in self.model._all.values() if r.meta.state == RECORDING]
        if self.recorder_panel.session is None and recording:
            sess = recorder.active(self.library)
            if sess is not None:
                self.recorder_panel.attach(sess)
        self._recover_orphans(recording)
        self._update_title()
        self._update_worker_label()
        self._update_actions()

    def _recover_orphans(self, recording):
        """A recording whose recorder died while the window is open is repaired right away."""
        if getattr(self, "_recovering", False):
            return
        orphans = [r for r in recording if not recorder.Session(r).alive()]
        if not orphans:
            return
        self._recovering = True
        lib = self.library

        def done(actions):
            self._recovering = False
            if any(a in ("finalized", "adopted") for _rid, a in actions):
                self.show_message("Recovered a recording after the recorder stopped unexpectedly.")
            self._refresh()

        def failed(msg):
            self._recovering = False
            self.show_message(f"Recovery problem: {msg}")

        # Give a just-stopped recorder time to finish saving before treating it as dead.
        QTimer.singleShot(1500, lambda: run_task(recorder.recover_all, lib, on_done=done, on_error=failed))

    def _update_empty(self):
        empty = self.model.rowCount() == 0
        if empty:
            self.empty.setText("No matches." if self.search.text() else
                               "No recordings yet.\n\nPress Record (Ctrl+R),\nor drop audio files here.")
            self.empty.resize(self.list.viewport().size())
            self.empty.move(0, 0)
        self.empty.setVisible(empty)
        n = self.model.total
        shown = self.model.rowCount()
        self.list_label.setText("RECORDINGS" + (f"  ·  {shown} OF {n}" if self.search.text() else f"  ·  {n}" if n else ""))

    def _update_title(self):
        sess = self.recorder_panel.session
        if sess is not None:
            st = sess.status()
            label = "Paused" if st.get("state") == recorder.S_PAUSED else "Recording"
            t = fmt_duration(st.get("elapsed", 0), always_hours=True)
            self.setWindowTitle(f"● {label} {t} — {APP_NAME}")
            self.tray.setToolTip(f"{APP_NAME}: {label.lower()} {t}")
            self.tray.setIcon(dot_icon(RECORD_RED, 64, ring=label == "Paused"))
            self.tray.show()
            self.a_record.setText("&Stop recording")
        else:
            self.setWindowTitle(APP_NAME)
            self.tray.setToolTip(APP_NAME)
            self.tray.setIcon(app_icon())
            self.tray.setVisible(not self.isVisible())
            self.a_record.setText("&Record")
        self.tray_stop.setEnabled(sess is not None)
        self.a_pause.setEnabled(sess is not None)

    def _update_worker_label(self):
        if not features.transcription_installed():
            self.worker_label.setText("Transcription not installed")
            return
        busy = [r for r in self.model._all.values() if r.meta.state == READY and r.transcript_status() in (T_RUNNING, T_QUEUED)]
        if busy and not transcription.worker_running(self.library):
            transcription.ensure_worker(self.library)  # e.g. after another folder's worker handed over
        if busy:
            self.worker_label.setText(f"Transcribing · {len(busy)} in queue" if len(busy) > 1 else "Transcribing")
        elif transcription.worker_running(self.library):
            self.worker_label.setText("Transcriber ready")
        else:
            self.worker_label.setText("")

    def _update_actions(self):
        rec = self.current()
        ready = rec is not None and rec.meta.state == READY
        for a in (self.a_export_audio, self.a_transcribe):
            a.setEnabled(ready)
        self.a_export_text.setEnabled(self.transcript.has_text())
        self.a_copy.setEnabled(self.transcript.has_text())
        self.a_cancel.setEnabled(ready and rec.transcript_status() in (T_RUNNING, T_QUEUED))
        self.a_rename.setEnabled(rec is not None)
        self.a_delete.setEnabled(rec is not None and rec.meta.state != RECORDING)
        self.a_folder.setEnabled(rec is not None)

    # ---- selection ----
    def current(self) -> Recording | None:
        idx = self.list.currentIndex()
        return self.model.recording(idx.row()) if idx.isValid() else None

    def _select(self, rid: str):
        self.model.refresh()
        row = self.model.row_of(rid)
        if row >= 0:
            self.list.selectionModel().setCurrentIndex(self.model.index(row),
                                                       QItemSelectionModel.SelectionFlag.ClearAndSelect)
            self.list.scrollTo(self.model.index(row))

    def _selection_changed(self, current, _previous):
        rec = self.model.recording(current.row()) if current.isValid() else None
        if rec is not None and rec.id == self._last_selected:
            return
        self._last_selected = rec.id if rec else None
        self.player.set_recording(rec)
        self.transcript.set_recording(rec)
        self._update_actions()

    # ---- recording events ----
    def _recording_started(self, rid: str):
        self._select(rid)
        self._update_title()

    def _recording_stopped(self, rid: str):
        self._update_title()
        QTimer.singleShot(400, self._refresh)

    # ---- search ----
    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _run_search(self):
        q = self.search.text().strip()
        if not q:
            self.model.set_filter(None)
            self._update_empty()
            return
        lib = self.library

        def query():
            idx = Index(lib)
            try:
                idx.sync()
                return {r["id"] for r in idx.list(q)}
            finally:
                idx.close()

        def done(ids):
            if self.search.text().strip() == q:
                self.model.set_filter(ids)
                self._update_empty()
                if self.model.rowCount() and not self.list.currentIndex().isValid():
                    self.list.setCurrentIndex(self.model.index(0))

        run_task(query, on_done=done, on_error=lambda m: self.show_message(f"Search failed: {m}"))

    # ---- import ----
    def import_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import audio", str(Path.home()),
            "Audio (" + " ".join(f"*{e}" for e in sorted(importer.AUDIO_EXTENSIONS)) + ");;All files (*)")
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
            return importer.import_paths(lib, paths, progress=lambda i, n, p: progress((i, n, p.name)))

        def on_progress(v):
            i, n, name = v
            if name:
                self.statusBar().showMessage(f"Importing {i + 1} of {n}: {name}")

        def done(results):
            imported = [r for r in results if r.status == importer.IMPORTED]
            dups = [r for r in results if r.status == importer.DUPLICATE]
            bad = [r for r in results if r.status == importer.REJECTED]
            self.model.refresh()
            if imported:
                self._select(imported[0].recording.id)
            parts = []
            if imported:
                parts.append(f"Imported {len(imported)}")
            if dups:
                parts.append(f"{len(dups)} already in the library")
            if bad:
                parts.append(f"{len(bad)} not imported")
            self.show_message(", ".join(parts) + "." if parts else "No audio files found.")
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

    # ---- actions on the selection ----
    def _context_menu(self, pos):
        idx = self.list.indexAt(pos)
        if not idx.isValid():
            return
        self.list.setCurrentIndex(idx)
        rec = self.model.recording(idx.row())
        if rec is None:
            return
        m = QMenu(self)
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

    def delete_selected(self):
        rec = self.current()
        if rec is None or rec.meta.state == RECORDING:
            return
        r = QMessageBox.question(self, "Delete recording",
                                 f"Move “{rec.meta.title}” and its transcript to the trash?\n"
                                 "You can restore it from the trash.")
        if r != QMessageBox.StandardButton.Yes:
            return
        row = self.list.currentIndex().row()
        if self.player.rec and self.player.rec.id == rec.id:
            self.player.set_recording(None)
            self.transcript.set_recording(None)
        transcription.cancel(rec)
        try:
            self.library.delete(rec)
        except OSError as e:
            self.show_message(f"Could not delete: {e}")
            return
        self.model.refresh()
        if self.model.rowCount():
            self.list.setCurrentIndex(self.model.index(min(row, self.model.rowCount() - 1)))
        self._last_selected = None
        self.show_message(f"Moved “{rec.meta.title}” to the trash.")

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

    def _crop_saved(self, rid: str):
        rec = self.library.get(rid)
        if rec and rec.transcript():
            self.show_message("Crop saved. Transcribe again to update the transcript for the new span.")

    def _seek_and_play(self, sec: float):
        self.player.seek(sec)
        if not self.player.is_playing():
            self.player.toggle_play()

    # ---- dialogs ----
    def show_settings(self):
        dlg = SettingsDialog(self.recorder_panel.session is not None, self)
        if dlg.exec() and getattr(dlg, "data_changed", False):
            QMessageBox.information(self, "Recordings folder",
                                    "Echo will use the new folder the next time it starts. "
                                    "Existing recordings stay where they are.")

    def show_model_dialog(self):
        ModelDialog(self).exec()
        self.transcript.refresh()

    def show_welcome(self):
        WelcomeDialog(self.recorder_panel, self).exec()
        self.transcript.refresh()

    # ---- window lifecycle ----
    def show_message(self, text: str):
        self.statusBar().showMessage(text, 8000)

    def show_window(self):
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()
        self._update_title()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange:
            self.recorder_panel.set_window_shown(self.isVisible() and not self.isMinimized())
        super().changeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self.recorder_panel.set_window_shown(not self.isMinimized())

    def hideEvent(self, e):
        super().hideEvent(e)
        self.recorder_panel.set_window_shown(False)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_empty()

    def closeEvent(self, e: QCloseEvent):
        self.transcript.save()
        self._save_state()
        if self._quitting:
            e.accept()
            return
        if self.recorder_panel.session is not None and QSystemTrayIcon.isSystemTrayAvailable():
            e.ignore()
            self.hide()
            self.tray.show()
            if not self._told_background:
                self.tray.showMessage(APP_NAME, "Still recording. Use the tray icon to show Echo or stop.",
                                      QSystemTrayIcon.MessageIcon.Information, 5000)
                self._told_background = True
            return
        if self.recorder_panel.session is not None:
            QMessageBox.information(self, APP_NAME, "The recording continues in the background. "
                                    "Open Echo again to stop it.")
        self._quitting = True
        self.shutdown()
        e.accept()
        QApplication.quit()

    def quit(self):
        if self.recorder_panel.session is not None:
            QMessageBox.information(self, APP_NAME, "The recording continues in the background. "
                                    "Open Echo again to stop it.")
        self._quitting = True
        self.transcript.save()
        self._save_state()
        self.shutdown()
        QApplication.quit()

    def shutdown(self):
        self._refresh_timer.stop()
        self.recorder_panel.shutdown()
        self.player.player.stop()
        self.player._timer.stop()
        self.tray.hide()

    def sizeHint(self) -> QSize:
        return QSize(1180, 760)
