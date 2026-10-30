"""Dialogs: welcome, model download, settings, setup check, shortcuts, about."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QProcess, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QProgressBar, QPushButton, QSpinBox, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__, dictionary, doctor, features, models, selfcmd, settings, transcription
from . import motion, theme
from .common import icon, run_task


def _heading(text: str, scale: float = 1.25) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(theme.display_font(scale, QFont.Weight.ExtraBold))
    lbl.setWordWrap(True)
    return lbl


def _dim(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setOpenExternalLinks(True)
    lbl.setTextFormat(Qt.TextFormat.RichText if "<" in text else Qt.TextFormat.PlainText)
    theme.set_role(lbl, dim=True)
    return lbl


class FittedDialog(QDialog):
    """Fixed-width dialog whose height follows its word-wrapped content.

    Top-level windows do not apply height-for-width by themselves, so wrapped labels would be
    clipped; the height is recomputed whenever the dialog is shown or its content changes.
    """

    def fit(self):
        lay = self.layout()
        if lay is None:
            return
        lay.invalidate()
        lay.activate()
        h = lay.totalHeightForWidth(self.width()) if lay.hasHeightForWidth() else lay.totalSizeHint().height()
        self.setMinimumHeight(h)
        self.resize(self.width(), h)

    def showEvent(self, e):
        super().showEvent(e)
        self.fit()


# ---- model download -----------------------------------------------------------------------------

def _downloaded_bytes(refs) -> int:
    total = 0
    for ref in refs:
        d = models.snapshot_dir(ref).parent.parent / "blobs"
        if d.is_dir():
            for f in d.iterdir():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    return total


class ModelDownload(QWidget):
    finished = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.info = _dim("")
        lay.addWidget(self.info)
        self.token_row = QWidget()
        tl = QHBoxLayout(self.token_row)
        tl.setContentsMargins(0, 0, 0, 0)
        self.token = QLineEdit()
        self.token.setPlaceholderText("Paste a Hugging Face access token (hf_…)")
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        tl.addWidget(self.token, 1)
        save = QPushButton("Save token")
        save.clicked.connect(self._save_token)
        tl.addWidget(save)
        lay.addWidget(self.token_row)
        row = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(True)
        row.addWidget(self.bar, 1)
        self.button = QPushButton(icon("download", "on_accent"), "Download (4.3 GB)")
        theme.set_role(self.button, primary=True)
        self.button.clicked.connect(self.start)
        row.addWidget(self.button)
        lay.addLayout(row)
        self.status = _dim("")
        lay.addWidget(self.status)
        self.proc: QProcess | None = None
        self._refs: list = []
        self._timer = QTimer(self, interval=500, timeout=self._poll)
        self.update_state()

    def update_state(self):
        installed = features.transcription_installed()
        cached = models.all_cached()
        speaker_only = cached and not models.speaker_cached()  # one small, ungated download left
        has_token = models.hf_token_present()
        self.token_row.setVisible(installed and not cached and not has_token)
        self.bar.setVisible(installed and (not cached or speaker_only))
        self.button.setVisible(installed and (not cached or speaker_only))
        self.button.setEnabled((has_token or speaker_only) and self.proc is None)
        size = f"{models.speaker_download_mb()} MB" if speaker_only else "4.3 GB"
        self.button.setText(f"Download ({size})")
        if not installed:
            self.info.setText("Transcription is not installed on this computer. To add it, run in the Echo folder:\n"
                              "./install.sh --with-transcription")
        elif speaker_only:
            self.info.setText(f"The transcription model is ready. One more small download "
                              f"({models.speaker_download_mb()} MB) lets Echo tell speakers apart in interviews "
                              "and meetings.")
        elif cached:
            speed = transcription.speed_text()
            self.info.setText("The transcription model is downloaded and ready." + (f" {speed}" if speed else ""))
            self.status.setText("")
        elif not has_token:
            self.info.setText(
                "The model is free but gated: accept its terms on Hugging Face with your account, "
                f'on <a href="https://huggingface.co/{models.BASE.repo}">Cohere Transcribe</a> and '
                f'<a href="https://huggingface.co/{models.ADAPTER.repo}">the Surus Spanish adapter</a>. '
                'Then create a read token at <a href="https://huggingface.co/settings/tokens">'
                "huggingface.co/settings/tokens</a> and paste it here.")
            self.info.setTextFormat(Qt.TextFormat.RichText)
        else:
            speed = transcription.speed_text()
            self.info.setText("Download the transcription model once (about 4.3 GB). After that, everything runs on "
                              "this computer and nothing is sent anywhere." + (f" {speed}" if speed else ""))

    def _save_token(self):
        tok = self.token.text().strip()
        if not tok.startswith("hf_") or len(tok) < 20:
            self.status.setText("That does not look like a Hugging Face token (they start with hf_).")
            return
        path = models.hf_home() / "token"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(tok)
        self.token.clear()
        self.status.setText("Token saved.")
        self.update_state()

    def start(self):
        if self.proc is not None:
            return
        self._refs = models.missing()
        self.proc = QProcess(self)
        cmd = selfcmd.command("models", "download")
        env = selfcmd.env()
        from PySide6.QtCore import QProcessEnvironment

        qenv = QProcessEnvironment()
        for k, v in env.items():
            qenv.insert(k, v)
        self.proc.setProcessEnvironment(qenv)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.finished.connect(self._done)
        self.proc.start(cmd[0], cmd[1:])
        self.button.setEnabled(False)
        self.button.setText("Downloading…")
        self.status.setText("Downloading. You can keep using Echo meanwhile.")
        self._timer.start()

    def _poll(self):
        total = sum(r.approx_bytes for r in self._refs)
        got = _downloaded_bytes(self._refs)
        frac = min(0.99, got / total) if total else 0
        self.bar.setValue(int(frac * 1000))
        self.bar.setFormat(f"{got / 1e9:.1f} of {total / 1e9:.1f} GB")

    def _done(self, code, _status):
        self._timer.stop()
        out = bytes(self.proc.readAll()).decode(errors="replace").strip() if self.proc else ""
        self.proc = None
        ok = code == 0 and models.all_cached()
        if ok:
            self.bar.setValue(1000)
            self.status.setText("Model ready.")
        else:
            last = out.splitlines()[-3:] if out else ["Unknown error"]
            self.status.setText("Download failed: " + " ".join(last))
        self.update_state()
        self.finished.emit(ok)

    def stop(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.waitForFinished(2000)


class ModelDialog(FittedDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Transcription model")
        self.setFixedWidth(560)
        lay = QVBoxLayout(self)
        lay.addWidget(_heading("Transcription model"))
        self.dl = ModelDownload()
        lay.addWidget(self.dl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def reject(self):
        # Closing does not cancel a running download; it continues in its own process.
        super().reject()


# ---- welcome ------------------------------------------------------------------------------------

class WaveBanner(QWidget):
    """The deep gradient with the wordmark, a line of copy and still waves."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 58)
        lay.setSpacing(6)
        from .common import Wordmark

        lay.addWidget(Wordmark(2.6))
        self.text = QLabel(text)
        self.text.setWordWrap(True)
        self.text.setFont(theme.display_font(1.05, QFont.Weight.DemiBold))
        lay.addWidget(self.text)
        self.text.setStyleSheet("background: transparent;")
        self._style()

    def _style(self):
        t = theme.current()
        self.setStyleSheet(f"QLabel {{ color: {t.on_deep}; background: transparent; }}")

    def paintEvent(self, _):
        p = QPainter(self)
        r = QRectF(self.rect())
        p.fillRect(r, theme.deep_gradient(r))
        theme.paint_waves(p, QRectF(0, r.height() - 64, r.width(), 64), 1.3, 0.35)
        p.end()


class WelcomeDialog(FittedDialog):
    def __init__(self, recorder_panel, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Welcome to {APP_NAME}")
        self.setFixedWidth(600)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(WaveBanner("Record long talks and voice notes, drop in audio from WhatsApp or anywhere "
                                   "else, and get Spanish transcripts made on this computer."))
        body = QWidget()
        outer.addWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(12)
        lay.addWidget(_heading("1. Check your microphone", 1.1))
        lay.addWidget(_dim("Pick the input below and speak; the meter should move. You can change it later at the top "
                           "left of the window."))
        mic = QHBoxLayout()
        self.source = QComboBox()
        self._panel = recorder_panel
        self._mirror_sources()
        self.source.activated.connect(self._pick)
        mic.addWidget(self.source, 1)
        lay.addLayout(mic)
        from .inputs import LevelMeter

        self.meter = LevelMeter(on_deep=False)
        lay.addWidget(self.meter)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        theme.set_role(self.hint, warn=True)
        self.hint.hide()
        lay.addWidget(self.hint)
        self._meter_timer = QTimer(self, interval=60, timeout=self._mirror_meter)
        self._meter_timer.start()
        lay.addWidget(_heading("2. Transcription model", 1.1))
        self.dl = ModelDownload()
        lay.addWidget(self.dl)
        lay.addWidget(_dim("Tip: closing this window keeps the recorder fully usable; you can download the model later "
                           "from Help → Transcription model."))
        bb = QDialogButtonBox()
        start = bb.addButton("Start using Echo", QDialogButtonBox.ButtonRole.AcceptRole)
        start.setDefault(True)
        theme.set_role(start, primary=True)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)

    def _mirror_sources(self):
        p = self._panel.source
        self.source.clear()
        for i in range(p.count()):
            if p.itemData(i) is None and not p.itemText(i):
                self.source.insertSeparator(self.source.count())
            else:
                self.source.addItem(p.itemText(i), p.itemData(i))
        self.source.setCurrentIndex(p.currentIndex())

    def _pick(self, idx):
        self._panel.source.setCurrentIndex(idx)
        self._panel._source_chosen(idx)

    def _mirror_meter(self):
        if self.source.count() != self._panel.source.count():
            self._mirror_sources()
        m = self._panel.meter
        self.meter._level, self.meter._hold, self.meter._clip_until = m._level, m._hold, m._clip_until
        self.meter.update()
        hint = (self._panel.warning.text() if self._panel.warning.isVisibleTo(self._panel) else "") \
            or self._panel.silence
        if hint != self.hint.text() or bool(hint) != self.hint.isVisibleTo(self):
            self.hint.setText(hint)
            self.hint.setVisible(bool(hint))
            self.fit()

    def done(self, r):
        self._meter_timer.stop()
        super().done(r)


# ---- settings -----------------------------------------------------------------------------------

class DictionaryPage(QWidget):
    """The whole dictionary, for repair: remove, merge, import. Entries are learned elsewhere."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dic = dictionary.load()
        lay = QVBoxLayout(self)
        lay.addWidget(_dim("Names and terms Echo spells as written here, in new transcripts and in existing ones. "
                           "They are learned when you correct a transcript or name a recording; this list is for "
                           "tidying up."))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Kind", "Also written as", "Last used"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setAlternatingRowColors(False)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.remove_btn = QPushButton(icon("delete"), "Remove")
        self.remove_btn.clicked.connect(self._remove)
        self.merge_btn = QPushButton("Merge…")
        self.merge_btn.setToolTip("Keep one of the selected entries, with the spellings of all of them")
        self.merge_btn.clicked.connect(self._merge)
        imp = QPushButton(icon("import"), "Import from a text file…")
        imp.setToolTip("One name or term per line")
        imp.clicked.connect(self._import)
        row.addWidget(self.remove_btn)
        row.addWidget(self.merge_btn)
        row.addStretch(1)
        row.addWidget(imp)
        lay.addLayout(row)
        self.muted = _dim("")
        lay.addWidget(self.muted)
        self.changed = False
        self._fill()

    def _fill(self):
        self.tree.clear()
        for e in sorted(self.dic.entries, key=lambda e: dictionary.fold(e.name)):
            used = e.used[:10] if e.used else "never"
            it = QTreeWidgetItem([e.name, "person" if e.kind == dictionary.PEOPLE else "term", ", ".join(e.aliases),
                                  used])
            it.setData(0, Qt.ItemDataRole.UserRole, e.name)
            self.tree.addTopLevelItem(it)
        for c in range(4):
            if c != 2:
                self.tree.resizeColumnToContents(c)
        n = len(self.dic.muted)
        self.muted.setText(f"{n} word{'s' if n != 1 else ''} will not be suggested again." if n else "")
        self._update_buttons()

    def _selected(self) -> list[str]:
        return [it.data(0, Qt.ItemDataRole.UserRole) for it in self.tree.selectedItems()]

    def _update_buttons(self):
        n = len(self._selected())
        self.remove_btn.setEnabled(n >= 1)
        self.merge_btn.setEnabled(n >= 2)

    def _remove(self):
        for name in self._selected():
            self.dic.remove(name)
        self.changed = True
        self._fill()

    def _merge(self):
        names = self._selected()
        keep, ok = QInputDialog.getItem(self, "Merge entries", "Keep this spelling:", names, 0, False)
        if not ok:
            return
        for name in names:
            if name != keep:
                self.dic.merge(name, keep)
        self.changed = True
        self._fill()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import names and terms", str(Path.home()),
                                              "Text (*.txt);;All files (*)")
        if not path:
            return
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            self.muted.setText(f"Could not read that file: {e}")
            return
        added = 0
        for line in lines:
            name = " ".join(line.split())
            if name and not name.startswith("#") and self.dic.find(name) is None:
                self.dic.add(dictionary.kind_of(name), name)
                added += 1
        self.changed = self.changed or bool(added)
        self._fill()
        self.muted.setText(f"Imported {added} new entr{'ies' if added != 1 else 'y'}.")

    def save(self):
        if self.changed:
            self.dic.save()


class WatchedFoldersPage(QWidget):
    """Folders Echo imports new audio files from by itself."""

    def __init__(self, folders: list[str], parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(_dim("New audio files that appear in these folders are imported while Echo runs, for example "
                           "where your phone syncs voice notes or WhatsApp exports land. The files stay where they are; "
                           "duplicates are skipped. Subfolders are not watched."))
        self.list = QListWidget()
        for f in folders:
            self.list.addItem(f)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        add = QPushButton(icon("folder"), "Add folder…")
        add.clicked.connect(self._add)
        self.remove = QPushButton(icon("delete"), "Remove")
        self.remove.clicked.connect(lambda: [self.list.takeItem(self.list.row(i)) for i in self.list.selectedItems()])
        row.addWidget(add)
        row.addWidget(self.remove)
        row.addStretch(1)
        lay.addLayout(row)

    def _add(self):
        d = QFileDialog.getExistingDirectory(self, "Watch a folder", str(Path.home()))
        if d and d not in self.folders():
            self.list.addItem(d)

    def folders(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]


class ExportLibraryDialog(FittedDialog):
    """Markdown notes for a vault: where, what, and whether to keep them up to date."""

    def __init__(self, has_selection: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export library to folder")
        self.setFixedWidth(560)
        cfg, _ = settings.load()
        lay = QVBoxLayout(self)
        lay.addWidget(_heading("Export as Markdown notes"))
        lay.addWidget(_dim("One note per recording, with its title, date, tags, the people named in it, markers as "
                           "headings and a link to the audio, for Obsidian or any folder of Markdown files. Notes "
                           "already up to date are left alone."))
        form = QFormLayout()
        row = QHBoxLayout()
        self.folder = QLineEdit(cfg.export_dir or str(Path.home() / "Notes" / "Echo"))
        row.addWidget(self.folder, 1)
        browse = QPushButton(icon("folder"), "Choose…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        w = QWidget()
        row.setContentsMargins(0, 0, 0, 0)
        w.setLayout(row)
        form.addRow("Folder", w)
        self.which = QComboBox()
        self.which.addItem("All recordings", "all")
        if has_selection:
            self.which.addItem("The selected recording", "selected")
        form.addRow("Export", self.which)
        self.audio = QComboBox()
        for label, value in (("Link to Echo's file", "link"), ("Copy next to the notes", "copy"), ("None", "none")):
            self.audio.addItem(label, value)
        self.audio.setCurrentIndex(max(0, self.audio.findData(cfg.export_audio)))
        form.addRow("Audio", self.audio)
        self.times = QCheckBox("Start each paragraph with its time")
        self.times.setChecked(cfg.export_timestamps)
        form.addRow("", self.times)
        self.sync = QCheckBox("Keep this folder up to date while Echo runs")
        self.sync.setChecked(cfg.export_sync)
        self.sync.setToolTip("Echo rewrites a recording's note a moment after it changes. It writes outside its own "
                             "folder only here.")
        form.addRow("", self.sync)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        ok = bb.addButton("Export", QDialogButtonBox.ButtonRole.AcceptRole)
        theme.set_role(ok, primary=True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Export to", self.folder.text())
        if d:
            self.folder.setText(d)

    def accept(self):
        cfg, _ = settings.load()
        cfg.export_dir = str(Path(self.folder.text()).expanduser())
        cfg.export_audio = self.audio.currentData()
        cfg.export_timestamps = self.times.isChecked()
        cfg.export_sync = self.sync.isChecked()
        settings.save(cfg)
        super().accept()


class SettingsDialog(QDialog):
    def __init__(self, recording_active: bool, parent=None, pages=()):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)
        self.cfg, _ = settings.load()
        self._old_data = self.cfg.data_path
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        general = QWidget()
        lay = QVBoxLayout(general)
        self.tabs.addTab(general, "General")
        self.dictionary = DictionaryPage()
        self.tabs.addTab(self.dictionary, "Dictionary")
        self.watched = WatchedFoldersPage(self.cfg.watch_dirs)
        self.tabs.addTab(self.watched, "Import")
        # Pages from extensions; each one's apply() saves it on OK.
        self.pages = list(pages)
        for title, page in self.pages:
            self.tabs.addTab(page, title)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.your_name = QLineEdit(self.cfg.your_name)
        self.your_name.setPlaceholderText("Echo names you in transcripts once it knows your voice")
        self.your_name.setToolTip("Echo learns your voice when you answer \"It's me\" for a speaker, and from the "
                                  "microphone side of recorded calls. Voices stay on this computer.")
        form.addRow("Your name", self.your_name)
        row = QHBoxLayout()
        self.data_dir = QLineEdit(str(self.cfg.data_path))
        row.addWidget(self.data_dir, 1)
        browse = QPushButton(icon("folder"), "Choose…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        form.addRow("Recordings folder", w)
        self.theme = QComboBox()
        for label, value in (("Light", theme.LIGHT), ("Dark", theme.DARK), ("Match the system", theme.SYSTEM)):
            self.theme.addItem(label, value)
        self.theme.setCurrentIndex(max(0, self.theme.findData(self.cfg.theme)))
        self._mode_on_open = theme.mode()
        self.theme.currentIndexChanged.connect(lambda _i: theme.apply(self.theme.currentData()))
        form.addRow("Appearance", self.theme)
        self.reduce_motion = QCheckBox("Reduce motion")
        self.reduce_motion.setToolTip("No animations. Echo also turns them off when the desktop has them off.")
        self.reduce_motion.setChecked(self.cfg.reduce_motion)
        form.addRow("", self.reduce_motion)
        if recording_active:
            self.data_dir.setEnabled(False)
            browse.setEnabled(False)
        self.rate = QComboBox()
        for r in (48000, 44100):
            self.rate.addItem(f"{r / 1000:g} kHz", r)
        self.rate.setCurrentIndex(max(0, self.rate.findData(self.cfg.sample_rate)))
        form.addRow("Sample rate", self.rate)
        self.channels = QComboBox()
        self.channels.addItem("Mono (recommended for speech)", 1)
        self.channels.addItem("Stereo", 2)
        self.channels.setCurrentIndex(max(0, self.channels.findData(self.cfg.channels)))
        form.addRow("Channels", self.channels)
        self.auto = QCheckBox("Transcribe new recordings and imports automatically")
        self.auto.setChecked(self.cfg.auto_transcribe)
        form.addRow("Transcription", self.auto)
        self.language = QComboBox()
        for code in models.supported_languages():
            self.language.addItem(models.language_name(code), code)
        self.language.setCurrentIndex(max(0, self.language.findData(self.cfg.language)))
        self.language.setToolTip("Language of new recordings and imports. Each recording can be changed in the "
                                 "transcript's menu.")
        form.addRow("Transcription language", self.language)
        self.adapter = QCheckBox("Use the Spanish robustness adapter")
        self.adapter.setChecked(self.cfg.use_adapter)
        self.adapter.setToolTip("Improves accuracy on noisy or phone-quality audio such as voice notes; "
                                "about the same on clean audio.")
        form.addRow("", self.adapter)
        self.shortcuts = QCheckBox("Ctrl+Alt+R records and Ctrl+Alt+N takes a quick note, from any application")
        self.shortcuts.setChecked(self.cfg.global_shortcuts)
        self.shortcuts.setToolTip("Through your desktop's shortcuts portal, which asks once to confirm the keys. "
                                  "A quick note records until you press the keys again, then its text is copied "
                                  "to the clipboard when it is transcribed.")
        form.addRow("Shortcuts", self.shortcuts)
        self.shortcuts_note = _dim("")
        form.addRow("", self.shortcuts_note)
        self._explain_shortcuts()
        self.autopause = QCheckBox("Pause playback while typing, replay the passage after")
        self.autopause.setChecked(self.cfg.edit_autopause)
        self.autopause.setToolTip("When a passage plays with Ctrl+. and you start typing, it pauses, and plays "
                                  "again from its start a second after you stop.")
        form.addRow("Editing", self.autopause)
        self.idle = QSpinBox()
        self.idle.setRange(1, 240)
        self.idle.setSuffix(" min")
        self.idle.setValue(self.cfg.worker_idle_minutes)
        self.idle.setToolTip("How long the transcriber stays loaded after its last job before freeing GPU memory.")
        form.addRow("Free GPU memory after", self.idle)
        lay.addLayout(form)
        if not features.transcription_installed():
            for wdg in (self.auto, self.adapter, self.idle, self.language):
                wdg.setEnabled(False)
            lay.addWidget(_dim("Transcription is not installed (./install.sh --with-transcription)."))
        lay.addStretch(1)
        self.note = _dim("")
        outer.addWidget(self.note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

    def _explain_shortcuts(self):
        import os

        from .shortcuts import available

        if os.environ.get("ECHO_NO_PORTAL") or not available():
            self.shortcuts.setEnabled(False)
            self.shortcuts_note.setText(
                "Your desktop has no global shortcuts portal. Bind keys to <code>echo-app record --toggle</code> "
                "and <code>echo-app record --quick-note</code> in its keyboard settings instead.")
            self.shortcuts_note.setTextFormat(Qt.TextFormat.RichText)
            self.shortcuts_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        else:
            self.shortcuts_note.hide()

    def reject(self):
        if theme.mode() != self._mode_on_open:
            theme.apply(self._mode_on_open)  # undo the live preview
        super().reject()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Recordings folder", self.data_dir.text())
        if d:
            self.data_dir.setText(d)

    def accept(self):
        new_dir = Path(self.data_dir.text()).expanduser()
        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            probe = new_dir / ".write-test"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError as e:
            self.note.setText(f"That folder cannot be used: {e}")
            return
        from .. import paths

        self.cfg.data_dir = "" if new_dir == paths.default_data_dir() else str(new_dir)
        self.cfg.sample_rate = self.rate.currentData()
        name = " ".join(self.your_name.text().split())
        if self.cfg.your_name and name and name != self.cfg.your_name:
            dictionary.rename_voice(self.cfg.your_name, name)
        self.cfg.your_name = name
        self.cfg.channels = self.channels.currentData()
        self.cfg.auto_transcribe = self.auto.isChecked()
        self.cfg.use_adapter = self.adapter.isChecked()
        self.cfg.watch_dirs = self.watched.folders()
        self.cfg.edit_autopause = self.autopause.isChecked()
        self.cfg.global_shortcuts = self.shortcuts.isChecked()
        self.cfg.language = self.language.currentData() or "es"
        self.cfg.worker_idle_minutes = self.idle.value()
        self.cfg.theme = self.theme.currentData()
        self.cfg.reduce_motion = self.reduce_motion.isChecked()
        settings.save(self.cfg)
        motion.refresh()
        try:
            self.dictionary.save()
        except OSError as e:
            self.note.setText(f"Could not save the dictionary: {e}")
            return
        for title, page in self.pages:
            apply = getattr(page, "apply", None)
            if apply is None:
                continue
            try:
                apply()
            except ValueError as e:
                self.tabs.setCurrentWidget(page)
                self.note.setText(f"{title}: {e}")
                return
        self.data_changed = self.cfg.data_path != self._old_data
        super().accept()


# ---- setup check --------------------------------------------------------------------------------

class DoctorDialog(FittedDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Check setup")
        self.setFixedWidth(680)
        lay = QVBoxLayout(self)
        lay.addWidget(_heading("Check setup"))
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setColumnStretch(2, 1)
        lay.addWidget(self.grid_host)
        self.wait = _dim("Checking…")
        lay.addWidget(self.wait)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_btn = bb.addButton("Copy report", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_btn.clicked.connect(self._copy)
        self.copy_btn.setEnabled(False)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._checks = []
        run_task(doctor.run_all, True, on_done=self._show, on_error=lambda m: self.wait.setText(f"Check failed: {m}"))

    def _show(self, checks):
        self._checks = checks
        self.wait.hide()
        names = {doctor.OK: "ok", doctor.WARN: "warning", doctor.FAIL: "error"}
        for r, c in enumerate(checks):
            ic = QLabel()
            ic.setPixmap(icon(names[c.status]).pixmap(16, 16))
            self.grid.addWidget(ic, r, 0, Qt.AlignmentFlag.AlignTop)
            name = QLabel(f"<b>{c.name}</b>")
            self.grid.addWidget(name, r, 1, Qt.AlignmentFlag.AlignTop)
            detail = c.detail.replace("/", "/\u200b")  # let long paths wrap
            text = detail + (f"<br><span style='opacity:.75'>{c.fix}</span>" if c.fix and c.status != doctor.OK else "")
            d = QLabel(text)
            d.setWordWrap(True)
            d.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.grid.addWidget(d, r, 2)
        self.copy_btn.setEnabled(True)
        QTimer.singleShot(0, self.fit)

    def _copy(self):
        QGuiApplication.clipboard().setText(doctor.render(self._checks, color=False))


# ---- shortcuts and about ------------------------------------------------------------------------

SHORTCUTS = [
    ("Record / stop", "Ctrl+R"),
    ("Pause / resume recording", "Ctrl+Shift+R"),
    ("Add a marker while recording", "M (or the tray menu)"),
    ("Marker at the playhead", "Ctrl+M"),
    ("Next / previous marker", "Alt+→ / Alt+←"),
    ("Move or remove a marker", "Drag it; right-click it (waveform)"),
    ("Play / pause", "Space (outside the editor), Ctrl+Space anywhere"),
    ("Seek 5 s / 1 s", "← → / Shift+← → (waveform focused)"),
    ("Set crop start / end at playhead", "[ and ] (waveform focused)"),
    ("Nudge crop edge", "Ctrl+← → (0.1 s), Ctrl+Shift+← → (1 s)"),
    ("Jump to passage", "Ctrl+click in the transcript (edited text too)"),
    ("Play the passage at the cursor (again: stop)", "Ctrl+."),
    ("Next / previous passage, and play it", "Ctrl+Alt+. / Ctrl+Alt+,"),
    ("Next passage to check, and play it", "Ctrl+Shift+."),
    ("Find in transcript", "Ctrl+F"),
    ("Copy transcript", "Ctrl+Shift+C"),
    ("Copy with passage times", "Ctrl+Alt+C"),
    ("Show passage times", "Ctrl+T"),
    ("Export transcript", "Ctrl+E"),
    ("Import audio", "Ctrl+O"),
    ("Search all recordings (titles, notes, transcripts)", "Ctrl+Shift+F or Ctrl+K"),
    ("People: profiles, their recordings and voices", "Ctrl+Shift+P"),
    ("Select several recordings", "Ctrl+click, Shift+click"),
    ("Link the selected recordings into a set", "Ctrl+L, or drag one onto another"),
    ("Show or hide a set's parts", "→ / ← (list), or click its arrow"),
    ("Move a part within its set", "Alt+Shift+↑ / Alt+Shift+↓, or drag it"),
    ("Rename", "F2"),
    ("Delete (to trash)", "Delete"),
    ("Settings", "Ctrl+,"),
    ("Quit", "Ctrl+Q"),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        lay = QVBoxLayout(self)
        grid = QGridLayout()
        for r, (what, keys) in enumerate(SHORTCUTS):
            grid.addWidget(QLabel(what), r, 0)
            k = QLabel(f"<b>{keys}</b>")
            grid.addWidget(k, r, 1)
        lay.addLayout(grid)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class AboutDialog(QDialog):
    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(_heading(f"{APP_NAME} {__version__}", 1.4))
        lay.addWidget(_dim("Record long-form audio and transcribe Spanish speech locally."))
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(line)
        from .. import paths

        lay.addWidget(_dim(
            f'Speech recognition: <a href="https://huggingface.co/{models.BASE.repo}">Cohere Transcribe</a> '
            f'(Apache-2.0) with the <a href="https://huggingface.co/{models.ADAPTER.repo}">Surus Spanish adapter</a> '
            '(Apache-2.0). Speech detection: Silero VAD (MIT).'))
        lay.addWidget(_dim(f"Recordings: {data_dir}<br>Settings: {settings.settings_path()}<br>"
                           f"Logs: {paths.state_dir()}"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
