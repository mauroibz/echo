"""The main window: building it, its state, the selection, refreshing, dialogs and lifecycle."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QItemSelectionModel, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCompleter, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListView, QMainWindow, QMenu, QMessageBox, QSplitter,
                               QStackedWidget, QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME, features, importer, recorder, sets, settings, transcription
from ..index import Index, parse_query
from ..library import READY, RECORDING, T_QUEUED, T_RUNNING, Library, Recording
from . import motion, theme
from .common import RECORD_RED, UiState, app_icon, dot_icon, fmt_duration, icon, run_task
from .dialogs import AboutDialog, DoctorDialog, ModelDialog, SettingsDialog, ShortcutsDialog, WelcomeDialog
from .library_view import LibraryModel, RowDelegate
from .player import PlayerPanel
from .recorder_panel import RecorderPanel
from .tags import TagBar
from .watch import FolderWatcher
from .transcript import TranscriptPanel
from .window_capture import CaptureMixin
from .window_library import LibraryActionsMixin
from .window_parts import DropOverlay, Toast, ViewSwitch, _SpaceFilter
from .window_search import SearchImportMixin

log = logging.getLogger(__name__)


class MainWindow(LibraryActionsMixin, SearchImportMixin, CaptureMixin, QMainWindow):
    """The window: the sidebar with the recorder and the library beside the selected recording.
    Its actions on the list, search and import, and recording from outside the window are in the
    `window_*` mixins; this class builds the parts, keeps the state and follows the selection."""

    transcribed = Signal(str)  # a recording's transcript was written while the window runs

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
        self._screen_buttons: dict[QWidget, QToolButton] = {}  # add_screen's
        self._build_parts()
        self._build_layout()
        self._build_menus()
        self._build_tray()
        self._restore()
        self._refresh_timer = QTimer(self, interval=1000, timeout=self._refresh)
        self._refresh_timer.start()
        self._search_timer = QTimer(self, singleShot=True, interval=200, timeout=self._run_search)
        self.model.refresh()
        self._select_initial()
        self._attach_active()
        self._sync_ids: set[str] = set()
        self._sync_timer = QTimer(self, singleShot=True, interval=2000, timeout=self._sync_notes)
        self.model.recordings_changed.connect(self._notes_changed)
        # Linking changes no recording folder: a synced notes folder is brought up to date as a whole.
        self.model.sets_changed.connect(lambda: self._notes_changed(list(self.model._all)))
        self.model.recordings_changed.connect(self._deliver_quick_notes)
        self._transcript_times = {r.id: self._transcript_time(r) for r in self.model._all.values()}
        self.model.recordings_changed.connect(self._check_transcribed)
        self.model.recordings_changed.connect(self._shown_changed)
        self.shortcuts = None
        self.watcher = FolderWatcher(self.library, self)
        self.watcher.imported.connect(self._watched_import)
        QTimer.singleShot(0, self._startup_tasks)

    # ---- construction ----
    def _build_parts(self):
        """Make and connect the parts: recorder, search, tags, banner, list, player, transcript.
        Where they go is _build_layout's, which a window that lays them out differently overrides."""
        self.recorder_panel = RecorderPanel(self.library)
        self.recorder_panel.message.connect(self.show_message)
        self.recorder_panel.started.connect(self._recording_started)
        self.recorder_panel.stopped.connect(self._recording_stopped)
        self.recorder_panel.recording_changed.connect(lambda _r: self._update_title())
        self.people_btn = self._corner_button("users", "People (Ctrl+Shift+P)")
        self.people_btn.clicked.connect(lambda: self.open_people())
        self.menu_btn = self._corner_button("menu", "Menu (F10)")
        self.app_menu = QMenu(self)
        self.menu_btn.setMenu(self.app_menu)
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.recorder_panel.add_corner(self.people_btn)
        self.recorder_panel.add_corner(self.menu_btn)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search    Ctrl+K")
        self.search.setAccessibleName("Search recordings")
        self.search.addAction(icon("find", "on_deep_muted"), QLineEdit.ActionPosition.LeadingPosition)
        self._clear_search = self.search.addAction(icon("close", "on_deep"), QLineEdit.ActionPosition.TrailingPosition)
        self._clear_search.setToolTip("Clear (Esc)")
        self._clear_search.triggered.connect(self.search.clear)
        self._clear_search.setVisible(False)
        self.search.textChanged.connect(lambda t: self._clear_search.setVisible(bool(t)))
        self._tags_open = False
        self.filter_action = self.search.addAction(icon("filter", "on_deep_muted"),
                                                   QLineEdit.ActionPosition.TrailingPosition)
        self.filter_action.setToolTip("Filter by tag")
        self.filter_action.triggered.connect(self.toggle_tag_bar)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        # "@" offers the people who speak in the library; the rest of the search is left as typed.
        self._people = QCompleter([], self)
        self._people.setWidget(self.search)
        self._people.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._people.setFilterMode(Qt.MatchFlag.MatchContains)
        self._people.activated.connect(self._complete_person)
        self.search.textEdited.connect(self._offer_people)
        self._speech: dict[str, dict] = {}  # speaker search: per recording, speaker numbers and snippet

        self.model = LibraryModel(self.library, self)
        self.model.expanded = set(self.state.get("expanded") or [])
        self.model.modelReset.connect(lambda: QTimer.singleShot(0, self._update_empty))
        self.list = QListView()
        self.list.setModel(self.model)
        # A rebuilt list (a new recording, a set expanded) keeps what was selected. Connected after
        # setModel, so it runs after the view's own reset has cleared the selection.
        self.model.modelAboutToBeReset.connect(self._remember_selection)
        self.model.modelReset.connect(self._restore_selection)
        self.delegate = RowDelegate(self.list)
        self.list.setItemDelegate(self.delegate)
        motion.clock().tick.connect(lambda _t: self.list.viewport().update()
                                    if self.list.isVisible() and self.model.needs_frames() else None)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setDropIndicatorShown(True)
        self.list.setUniformItemSizes(False)  # month headings are shorter than rows
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setMouseTracking(True)
        self.list.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.selectionModel().currentChanged.connect(self._selection_changed)
        self.list.clicked.connect(lambda _i: self.show_screen(None))  # a screen hid the recording
        self.list.selectionModel().selectionChanged.connect(lambda *_a: self._update_selection_bar())
        self.model.drop_requested.connect(self._dropped)
        self.list.setAccessibleName("Recordings")
        self.list.viewport().installEventFilter(self)
        self.list.installEventFilter(self)
        self.empty = QLabel("No recordings yet.\n\nPress Record (Ctrl+R),\nor drop audio files here.", self.list)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        theme.set_role(self.empty, dim=True)

        self.tag_bar = TagBar()
        self.tag_bar.toggled.connect(self._toggle_tag)
        self.tag_bar.hide()
        # After an import: notes that look like one burst, offered for linking in one click.
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(10, 6, 4, 6)
        bl.setSpacing(6)
        glyph = QLabel()
        glyph.setPixmap(icon("set", "foam").pixmap(16, 16))
        bl.addWidget(glyph)
        self.banner_text = QLabel()
        self.banner_text.setWordWrap(True)
        self.banner_text.setTextFormat(Qt.TextFormat.RichText)
        self.banner_text.linkActivated.connect(lambda _l: self._select_offer())
        bl.addWidget(self.banner_text, 1)
        self.banner_link = QToolButton()
        self.banner_link.setObjectName("linkbtn")
        self.banner_link.setIcon(icon("link", "deep_top"))
        self.banner_link.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.banner_link.clicked.connect(self._accept_offer)
        bl.addWidget(self.banner_link)
        self.banner_close = QToolButton()
        self.banner_close.setIcon(icon("close", "on_deep"))
        self.banner_close.setToolTip("Not one conversation: don't ask again")
        self.banner_close.setAccessibleName("Dismiss")
        self.banner_close.clicked.connect(self._dismiss_offer)
        bl.addWidget(self.banner_close)
        self.banner.hide()
        self._offers: list[sets.Offer] = []
        self.list_label = QLabel("RECORDINGS")
        self.list_label.setFont(theme.display_font(0.78, QFont.Weight.ExtraBold))
        theme.set_role(self.list_label, eyebrow=True)
        # Several rows selected: link them (or delete them) in one click.
        self.selection_bar = QFrame()
        self.selection_bar.setObjectName("selectionbar")
        bl = QHBoxLayout(self.selection_bar)
        bl.setContentsMargins(14, 8, 10, 8)
        bl.setSpacing(6)
        self.selection_label = QLabel()
        self.selection_label.setFont(theme.display_font(0.9, QFont.Weight.Bold))
        bl.addWidget(self.selection_label, 1)
        self.link_btn = QToolButton()
        self.link_btn.setObjectName("linkbtn")
        self.link_btn.setText("Link")
        self.link_btn.setIcon(icon("link", "deep_top"))
        self.link_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.link_btn.setToolTip("Link them into one set, read and played in order (Ctrl+L)")
        self.link_btn.clicked.connect(self.link_selected)
        bl.addWidget(self.link_btn)
        self.bar_delete = QToolButton()
        self.bar_delete.setText("Delete…")
        self.bar_delete.setIcon(icon("delete", "on_deep"))
        self.bar_delete.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.bar_delete.clicked.connect(self.delete_selected)
        bl.addWidget(self.bar_delete)
        self.selection_bar.hide()

        self.player = PlayerPanel(self)
        self.player.hide()  # its parts are laid out one by one: header, dock, details
        self.player.message.connect(self.show_message)
        self.player.renamed.connect(lambda rid, _t: self.model.reload(rid))
        self.player.meta_changed.connect(self._meta_changed)
        self.player.renamed.connect(lambda rid, title: self.transcript.offer_title(rid, title))
        self.player.set_renamed.connect(self._rename_set)
        self.player.crop_saved.connect(self._crop_saved)
        self.player.export_requested.connect(self.export_audio)
        self.transcript = TranscriptPanel(self.library)
        self.transcript.message.connect(self.show_message)
        self.transcript.profile_requested.connect(self.open_people)
        self._people_dialog = None
        self.transcript.seek_requested.connect(self._seek_and_play)
        self.transcript.position_requested.connect(self.player.seek)
        self.transcript.download_requested.connect(self.show_model_dialog)
        self.transcript.changed.connect(self.model.reload)
        self.transcript.part_requested.connect(self._show_part)
        self.player.position_changed.connect(self.transcript.follow)
        self.transcript.attach_player(self.player)
        self.player.markers_changed.connect(lambda _rid: self.transcript.reload_markers())
        self.player.markers_changed.connect(lambda _rid: self.details.refresh())
        self.transcript.marker_clicked.connect(self._seek_and_play)
        # The transcript and the views extensions add next to it (add_view), one shown at a time.
        self.views = ViewSwitch(self.transcript)

        # The header's actions: copy, export (transcript or audio), Details, and the transcript's menu.
        self.copy_btn = self._head_button("copy", "Copy", "Copy the whole transcript (Ctrl+Shift+C)")
        self.copy_btn.clicked.connect(self.transcript.copy_all)
        self.export_btn = self._head_button("export", "Export", "Export the transcript or the audio")
        export_menu = QMenu(self.export_btn)
        export_menu.addAction(icon("export"), "Transcript…  (Ctrl+E)", self.transcript.export_text)
        self.export_audio_entry = export_menu.addAction(icon("export"), "Audio…", self.export_audio)
        self.export_btn.setMenu(export_menu)
        self.export_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self.details_btn = self._head_button("details", "", "Details: notes, markers, file (Ctrl+I)")
        self.details_btn.setCheckable(True)
        self.details_btn.toggled.connect(self.show_details)
        self.more_btn = self.transcript.more_btn
        self.more_btn.setObjectName("headbtn")
        self.transcript.toolbar.hide()  # its status goes to Details, its buttons to the header
        from .details import DetailsPanel

        self.details = DetailsPanel(self.player, self.transcript)
        self.details.seek_requested.connect(self._seek_and_play)
        self.details.hide()

        self.worker_label = QLabel("", self)  # what the worker does; the rows show it, so it is not laid out
        self.worker_label.hide()
        self.toast = Toast(self)
        self.overlay = DropOverlay(self)
        from .record_dock import RecordDock

        self.dock = RecordDock(self.recorder_panel, self.library)
        self.dock.open_window.connect(self._from_dock)
        self.dock.visibility_changed.connect(self._dock_shown)

        self._space = _SpaceFilter(self.player.toggle_play)
        self.list.installEventFilter(self._space)
        self.player.wave.installEventFilter(self._space)

    def _build_layout(self):
        """The sidebar (recorder, search, tags, list) beside the selected recording: its header,
        the transcript over the player, and Details at the right."""
        left = theme.DeepBackground()
        left.setObjectName("sidebar")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        ll.addWidget(self.recorder_panel)
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(14, 2, 14, 6)
        sl.setSpacing(10)
        for w in (self.search, self.tag_bar, self.banner):
            sl.addWidget(w)
        ll.addWidget(sw)
        ll.addWidget(self.list, 1)
        ll.addWidget(self.selection_bar)

        right = QWidget()
        right.setObjectName("content")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(28, 22, 24, 18)
        rl.setSpacing(16)
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(self.player.header, 1)
        for b in (self.copy_btn, self.export_btn, self.details_btn, self.more_btn):
            head.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        rl.addLayout(head)
        body = QHBoxLayout()
        body.setSpacing(16)
        self.reader = QFrame()
        self.reader.setObjectName("card")
        self.reader.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rd = QVBoxLayout(self.reader)
        rd.setContentsMargins(0, 0, 0, 0)
        rd.setSpacing(0)
        rd.addWidget(self.views, 1)
        rd.addWidget(self.player.dock)
        body.addWidget(self.reader, 1)
        self.details.setObjectName("card")
        body.addWidget(self.details)
        rl.addLayout(body, 1)
        self.content = right
        self.toast.setParent(right)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setObjectName("main")
        self.split.setHandleWidth(1)
        # The recording, or a screen an extension adds (add_screen) in its place.
        self.screens = QStackedWidget()
        self.screens.addWidget(right)
        self.split.addWidget(left)
        self.split.addWidget(self.screens)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setChildrenCollapsible(False)
        left.setMinimumWidth(280)
        self.setCentralWidget(self.split)

    def _restore_layout(self):
        self.split.setSizes(self.state.get("split") or [310, 870])
        self.details_btn.setChecked(bool(self.state.get("details")))

    def _save_layout(self):
        self.state.set("split", self.split.sizes())
        self.state.set("details", self.details_btn.isChecked())

    def _corner_button(self, ic: str, tip: str) -> QToolButton:
        b = QToolButton()
        b.setObjectName("flat")
        b.setIcon(icon(ic, "on_deep_muted"))
        b.setIconSize(QSize(18, 18))
        b.setFixedSize(36, 36)
        b.setToolTip(tip)
        b.setAccessibleName(tip.split(" (")[0])
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _head_button(self, ic: str, text: str, tip: str) -> QToolButton:
        b = QToolButton()
        b.setObjectName("headbtn" if text else "headicon")
        b.setIcon(icon(ic))
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text else
                             Qt.ToolButtonStyle.ToolButtonIconOnly)
        b.setToolTip(tip)
        b.setAccessibleName(text or tip.split(":")[0])
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def show_details(self, on: bool):
        """Details at the right of the transcript, open or closed (Ctrl+I); it slides."""
        if self.details_btn.isChecked() != on:
            self.details_btn.setChecked(on)  # its toggled signal comes back here
            return
        if hasattr(self, "a_details"):
            self.a_details.setChecked(on)
        if on and not self.details.isVisible():
            self.details.setMaximumWidth(0)
            self.details.show()
            self.details.refresh()
            motion.slide_width(self.details, self.details.WIDTH)
        elif not on and self.details.isVisible():
            def closed():
                if not self.details_btn.isChecked():  # not opened again while it slid
                    self.details.hide()
                    self.details.setMaximumWidth(self.details.WIDTH)

            motion.slide_width(self.details, 0, done=closed)

    def toggle_tag_bar(self):
        self._tags_open = not self._tags_open
        self._update_tags()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.place()

    def add_view(self, title: str, widget: QWidget):
        """A view an extension shows instead of the transcript, chosen with a switch over it."""
        self.views.add(title, widget)
        self.views.show_subject(self.current(), self.current_set())

    def add_screen(self, title: str, ic: str, widget: QWidget, shortcut: str | None = None) -> QToolButton:
        """A screen an extension shows in place of the selected recording (a list across recordings,
        a question box), opened by a button beside People. Pressing it again, or choosing a recording
        in the list, goes back. Returns the button."""
        tip = f"{title} ({shortcut})" if shortcut else title
        b = self._corner_button(ic, tip)
        b.setCheckable(True)
        b.toggled.connect(lambda on, w=widget: self.show_screen(w if on else None))
        self.recorder_panel.add_corner(b, before=self.menu_btn)
        self.screens.addWidget(widget)
        self._screen_buttons[widget] = b
        if shortcut:
            a = QAction(title, self)
            a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(lambda: b.toggle())
            self.addAction(a)
        return b

    def show_screen(self, widget: QWidget | None):
        """Show an extension's screen, or the selected recording (None)."""
        widget = widget if widget is not None and self.screens.indexOf(widget) > 0 else None
        self.screens.setCurrentWidget(widget or self.content)
        for w, b in self._screen_buttons.items():
            b.blockSignals(True)
            b.setChecked(w is widget)
            b.blockSignals(False)

    def show_recording(self, rid: str, at: float | None = None):
        """Select a recording and, with `at`, play it from there: for an extension that sends the user
        to a passage (a citation, an action item). Goes back from a screen to the recording."""
        if self.model.row_of(rid) < 0 and self.search.text():
            self.search.clear()  # the search hid it
            self._run_search()
        self.show_screen(None)
        self._select(rid)
        if at is not None and self.current() is not None and self.current().id == rid:
            self._seek_and_play(float(at))

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
        """The application menu, in the button at the top of the sidebar. The window holds every
        action too, so its shortcut works without the menu."""
        mb = self.app_menu
        f = mb.addMenu("&File")
        self._act(f, "&Import audio…", self.import_dialog, "Ctrl+O", "import")
        self.a_export_text = self._act(f, "&Export transcript…", self.transcript.export_text, "Ctrl+E", "export")
        self.a_export_audio = self._act(f, "Export &audio…", self.export_audio, None, "export")
        self._act(f, "Export &library to folder…", self.export_library, None, "export")
        self.a_folder = self._act(f, "Show in &folder", self.show_in_folder, None, "folder")
        f.addSeparator()
        self._act(f, "&Settings…", self.show_settings, "Ctrl+,", "settings")
        f.addSeparator()
        self._act(f, "&Quit", self.quit, "Ctrl+Q")

        e = mb.addMenu("&Edit")
        self.a_copy = self._act(e, "&Copy transcript", self.transcript.copy_all, "Ctrl+Shift+C", "copy")
        self.a_copy_times = self._act(e, "Copy with &timestamps", self.transcript.copy_with_timestamps, "Ctrl+Alt+C",
                                      "copy")
        self._act(e, "&Find in transcript…", self.transcript.open_find, "Ctrl+F", "find")
        e.addSeparator()
        self._act(e, "Play the passage at the cursor", self.transcript.play_passage, "Ctrl+.", "play")
        self._act(e, "Next passage", lambda: self.transcript.step_passage(1), "Ctrl+Alt+.", "skip-forward")
        self._act(e, "Previous passage", lambda: self.transcript.step_passage(-1), "Ctrl+Alt+,", "skip-back")
        self._act(e, "Next passage to check", self.transcript.play_next_flagged, "Ctrl+Shift+.", "warning")
        e.addSeparator()
        # Ctrl+Shift+F as in code editors (search everything; Ctrl+F finds in this one); Ctrl+K stays.
        a_search = self._act(e, "&Search all recordings", self._focus_search, "Ctrl+Shift+F", "find")
        a_search.setShortcuts([QKeySequence("Ctrl+Shift+F"), QKeySequence("Ctrl+K")])
        e.addSeparator()
        self.a_link = self._act(e, "&Link selected recordings", self.link_selected, "Ctrl+L", "link")
        self.a_part_up = self._act(e, "Move part up", lambda: self.move_part(-1), "Alt+Shift+Up")
        self.a_part_down = self._act(e, "Move part down", lambda: self.move_part(1), "Alt+Shift+Down")
        e.addSeparator()
        self.a_rename = self._act(e, "&Rename", self.player.focus_title, "F2", "rename")
        self.a_delete = self._act(e, "&Delete…", self.delete_selected, "Del", "delete")
        self.a_delete.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.list.addAction(self.a_delete)

        v = mb.addMenu("&View")
        self.a_times = self._act(v, "&Passage times", lambda on: self.transcript.set_show_timestamps(on), "Ctrl+T",
                                 "clock")
        self.a_times.setCheckable(True)
        self.a_times.setChecked(self.transcript.show_timestamps)
        self.transcript.timestamps_toggled.connect(self.a_times.setChecked)
        self.a_dock = self._act(v, "Recording d&ock", self.toggle_dock, "Ctrl+Shift+D", "mic")
        self.a_details = self._act(v, "&Details", lambda on: self.show_details(on), "Ctrl+I", "details")
        self.a_details.setCheckable(True)
        self.a_details.setChecked(self.details_btn.isChecked())
        first = self.transcript.more_menu.actions()[0]
        self.transcript.more_menu.insertAction(first, self.a_times)
        v.addSeparator()
        self._act(v, "P&eople…", self.open_people, "Ctrl+Shift+P", "users")

        r = mb.addMenu("&Recording")
        self.a_record = self._act(r, "&Record", self.recorder_panel.toggle_record, "Ctrl+R")
        self.a_record.setIcon(dot_icon(RECORD_RED))
        self.a_pause = self._act(r, "&Pause / resume", self.recorder_panel.toggle_pause, "Ctrl+Shift+R", "pause")
        # A plain letter: text fields keep it for typing, so it only marks outside them.
        self.a_mark = self._act(r, "Add &marker", self.recorder_panel.add_marker, "M", "bookmark")
        r.addSeparator()
        self._act(r, "Play / pause", self.player.toggle_play, "Ctrl+Space", "play")
        self.a_mark_here = self._act(r, "Marker at the playhead", self.player.add_marker_at_playhead, "Ctrl+M",
                                     "bookmark")
        self._act(r, "Next marker", lambda: self.player.jump_marker(1), "Alt+Right", "skip-forward")
        self._act(r, "Previous marker", lambda: self.player.jump_marker(-1), "Alt+Left", "skip-back")
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
        QShortcut(QKeySequence("F10"), self, activated=self.menu_btn.showMenu)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(dot_icon(RECORD_RED, 64), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Show Echo", self.show_window)
        self.tray_mark = menu.addAction("Add marker", self._tray_mark)
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
        self._restore_layout()
        self.player.set_speed(self.state.get("speed", 1.0))
        vols = self.state.get("volumes")
        self.player.volumes = {k: float(v) for k, v in (vols.items() if isinstance(vols, dict) else ())
                               if isinstance(v, (int, float))}

    def _save_state(self):
        if not self.isMaximized():
            g = self.geometry()
            self.state.set("geometry", [g.x(), g.y(), g.width(), g.height()])
        self.state.set("maximized", self.isMaximized())
        self._save_layout()
        self.state.set("speed", self.player.speed_value())
        self.state.set("volumes", self.player.volumes)
        key = self.current_key()
        if key:
            self.state.set("selected", key)
        self.state.set("expanded", sorted(self.model.expanded))
        self.state.save()

    def _select_initial(self):
        rid = self.state.get("selected")
        row = self.model.row_of(rid) if rid else -1
        if row < 0:
            row = self.model.first_row()
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
        self.watcher.configure()
        self._start_global_shortcuts()

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
        self._animate_list()
        self._update_empty()
        rec = self.current()
        linked = self.current_set()
        if linked is not None:
            self.player.set_linked(*linked)
            self.transcript.set_linked(*linked)
        elif rec is not None:
            fresh = self.library.get(rec.id)
            if fresh is None:
                self.player.set_recording(None)
                self.transcript.set_recording(None)
            else:
                self.player.set_recording(fresh)
                self.transcript.refresh()
        elif self.model.first_row() >= 0 and not self.list.currentIndex().isValid():
            self.list.setCurrentIndex(self.model.index(self.model.first_row()))
        recording = [r for r in self.model._all.values() if r.meta.state == RECORDING]
        if self.recorder_panel.session is None and recording:
            sess = recorder.active(self.library)
            if sess is not None:
                self.recorder_panel.attach(sess)
        self._recover_orphans(recording)
        self._update_title()
        self._update_worker_label()
        self._update_actions()
        self.details.refresh()

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

    def _update_tags(self):
        from ..library import fold_tag

        counts = self.model.tag_counts()
        active = {fold_tag(t) for t in parse_query(self.search.text())[1]}
        self.tag_bar.set_tags(counts, active, self.model.category_totals())
        # Behind the filter button, but never hidden while a tag filters the list.
        self.tag_bar.setVisible(bool(counts) and (self._tags_open or bool(active)))
        self.player.tags.set_known([t for t, _n in counts])

    def _toggle_tag(self, tag: str, on: bool):
        """A chip adds or removes #tag in the search box, which stays the one place the filter lives."""
        from ..library import fold_tag

        words = [w for w in self.search.text().split() if not (w.startswith("#") and fold_tag(w[1:]) == fold_tag(tag))]
        if on:
            words.append(f"#{tag}")
        self.search.setText(" ".join(words))

    def _update_empty(self):
        self._update_tags()
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
        self.tray_mark.setEnabled(sess is not None)
        self.a_pause.setEnabled(sess is not None)
        self.a_mark.setEnabled(sess is not None)

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
        linked = self.current_set() is not None
        ready = rec is not None and rec.meta.state == READY
        for a in (self.a_export_audio, self.a_transcribe):
            a.setEnabled(ready)
        self.a_export_text.setEnabled(self.transcript.has_text())
        self.copy_btn.setEnabled(self.transcript.has_text())
        self.export_audio_entry.setEnabled(ready)
        self.export_btn.setEnabled(ready or self.transcript.has_text())
        self.a_copy.setEnabled(self.transcript.has_text())
        self.a_copy_times.setEnabled(self.transcript.has_text())
        self.a_cancel.setEnabled(ready and rec.transcript_status() in (T_RUNNING, T_QUEUED))
        self.a_rename.setEnabled(rec is not None or linked)
        self.a_delete.setEnabled((rec is not None and rec.meta.state != RECORDING) or linked)
        self.a_folder.setEnabled(rec is not None)
        part = rec is not None and self.model.set_of(rec.id) is not None
        self.a_part_up.setEnabled(part)
        self.a_part_down.setEnabled(part)
        self._update_selection_bar()

    # ---- selection ----
    def current(self) -> Recording | None:
        """The recording selected (a part of a set too); None when a set row is selected."""
        idx = self.list.currentIndex()
        return self.model.recording(idx.row()) if idx.isValid() else None

    def current_set(self):
        """(LinkedSet, parts) when a set row is selected."""
        idx = self.list.currentIndex()
        return self.model.linked_set(idx.row()) if idx.isValid() else None

    def current_key(self) -> str | None:
        """The id of the selected row: a recording's or a set's."""
        idx = self.list.currentIndex()
        return self.model.row_id(idx.row()) if idx.isValid() else None

    def _remember_selection(self):
        self._kept_key = self.current_key()
        self._kept_selection = [self.model.row_id(i.row()) for i in self.list.selectionModel().selectedRows()]

    def _restore_selection(self):
        key = getattr(self, "_kept_key", None)
        row = self.model.row_of(key) if key else -1
        if row < 0 and key and not sets.is_set_id(key):
            # A recording that went into a set (or whose set was collapsed): select its set.
            sid = self.model.set_of(key)
            row = self.model.row_of(sid) if sid else -1
        if row < 0:
            return
        sm = self.list.selectionModel()
        sm.blockSignals(True)
        sm.setCurrentIndex(self.model.index(row), QItemSelectionModel.SelectionFlag.ClearAndSelect)
        for k in getattr(self, "_kept_selection", []):
            r = self.model.row_of(k) if k else -1
            if r >= 0:
                sm.select(self.model.index(r), QItemSelectionModel.SelectionFlag.Select)
        sm.blockSignals(False)
        self.list.viewport().update()
        if self.current_key() != self._last_selected:
            self._selection_changed(self.list.currentIndex(), None)

    def open_people(self, name: str | None = None):
        """The People window, one for the session; with a name, at that person's profile."""
        from .people import PeopleDialog

        if self._people_dialog is None:
            self._people_dialog = PeopleDialog(self.library, self)
            self._people_dialog.open_recording.connect(self._open_from_people)
        dlg = self._people_dialog
        if name:
            dlg.select(name)
        else:
            dlg.reload()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _open_from_people(self, rid: str):
        if self.model.row_of(rid) < 0 and self.search.text():
            self.search.clear()  # the search hid it
            self._run_search()
        self._select(rid)
        self.raise_()
        self.activateWindow()

    def _select(self, rid: str):
        self.model.refresh()
        row = self.model.row_of(rid)
        if row >= 0:
            self.list.selectionModel().setCurrentIndex(self.model.index(row),
                                                       QItemSelectionModel.SelectionFlag.ClearAndSelect)
            self.list.scrollTo(self.model.index(row))

    def _selection_changed(self, current, _previous):
        key = self.model.row_id(current.row()) if current.isValid() else None
        if key is not None and key == self._last_selected:
            self._update_actions()
            return
        self._last_selected = key
        linked = self.model.linked_set(current.row()) if current.isValid() else None
        if linked is not None:
            self.player.set_linked(*linked)
            self.transcript.set_linked(*linked)
        else:
            rec = self.model.recording(current.row()) if current.isValid() else None
            self.player.set_recording(rec)
            self.transcript.set_recording(rec)
        self.views.show_subject(self.current(), linked)
        self.details.refresh()
        self._carry_search()
        self._update_actions()

    # ---- recording, for extensions ----
    def recording_id(self) -> str | None:
        """The recording being made, if any."""
        sess = self.recorder_panel.session
        return sess.rec.id if sess is not None else None

    def start_recording(self, title: str | None = None) -> bool:
        """Start recording from the current source as the Record button does, for an extension (one
        that records the meetings in a calendar). `title` names the recording. False when one is
        already being made or starting; the recording's id comes with `recorder_panel.started`."""
        if self.recorder_panel.session is not None or self.recorder_panel._busy:
            return False
        self._next_title = title
        self.recorder_panel.start()
        return True

    def stop_recording(self) -> None:
        self.recorder_panel.stop()

    # ---- recording events ----
    def _recording_started(self, rid: str):
        title, self._next_title = getattr(self, "_next_title", None), None
        rec = self.library.get(rid) if title else None
        if rec is not None:
            rec.update(title=title, title_auto=False)
            self.model.refresh()
        self._select(rid)
        self._update_title()

    def _recording_stopped(self, rid: str):
        self._update_title()
        QTimer.singleShot(400, self._refresh)

    # ---- dialogs ----
    def show_settings(self):
        from .. import extensions

        dlg = SettingsDialog(self.recorder_panel.session is not None, self, extensions.gather("settings_pages"))
        accepted = dlg.exec()
        if accepted:
            self.watcher.configure()
        if accepted and getattr(dlg, "data_changed", False):
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
    def _set_shown(self, shown: bool):
        """Meters and animation run only while the window is on screen."""
        self.recorder_panel.set_window_shown(shown)
        motion.clock().set_shown(shown or self.dock.isVisible())

    def _animate_list(self):
        """Frames for the list while a row is arriving or a transcription runs (its sweep)."""
        if self.model.needs_frames():
            motion.clock().hold(self.list)
        else:
            motion.clock().release(self.list)

    def show_message(self, text: str, ms: int | None = None):
        self.toast.show_text(text, ms)

    def show_window(self):
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()
        self._update_title()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange:
            self._set_shown(self.isVisible() and not self.isMinimized())
        super().changeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self._set_shown(not self.isMinimized())

    def hideEvent(self, e):
        super().hideEvent(e)
        self._set_shown(False)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_empty()

    def closeEvent(self, e: QCloseEvent):
        self.transcript.save()
        self._save_state()
        if self._quitting:
            e.accept()
            return
        if self.recorder_panel.session is not None:
            # The recording goes on in the dock (and the tray, where there is one).
            e.ignore()
            self.hide()
            self.show_dock()
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray.show()
            return
        if settings.load()[0].background and QSystemTrayIcon.isSystemTrayAvailable():
            e.ignore()  # kept running in the tray; Quit in its menu ends Echo
            self.hide()
            self.tray.show()
            return
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
        self.dock.close()
        motion.clock().release(self.list)
        self.watcher.stop()
        if self.shortcuts is not None:
            self.shortcuts.stop()
        self.recorder_panel.shutdown()
        self.player.player.stop()
        self.player._timer.stop()
        self.tray.hide()

    def sizeHint(self) -> QSize:
        return QSize(1180, 760)
