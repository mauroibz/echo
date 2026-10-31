"""Studio in the window: the Summaries settings page and the Summary view beside the transcript."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QActionGroup, QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPlainTextEdit, QPushButton, QScrollArea,
                               QToolButton, QVBoxLayout, QWidget)

from echo_app.ui import theme
from echo_app.ui.common import icon, run_task

from . import config, followup, keychain, llm, summary, templates
from .actions_ui import ActionList
from .reading import ReadingBrowser

VIEW_TITLE = "Minutes"
ACTIONS_MAX_H = 260


def _dim(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    theme.set_role(lbl, dim=True)
    return lbl


class SettingsPage(QWidget):
    """Server address, model and key. Saving with both set turns summaries on."""

    def __init__(self, on_saved=None):
        super().__init__()
        self.on_saved = on_saved
        cfg = config.load()
        lay = QVBoxLayout(self)
        lay.addWidget(_dim("Summaries are written by a language model on a server you choose: one on this "
                           "computer (llama.cpp, Ollama, vLLM), Anthropic (https://api.anthropic.com/v1) or "
                           "another cloud provider with an OpenAI-compatible API. Leave the address "
                           "empty to turn them off."))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.url = QLineEdit(cfg.llm_url)
        self.url.setPlaceholderText("http://127.0.0.1:8080/v1")
        self.url.textChanged.connect(self._update_warning)
        form.addRow("Server address", self.url)
        self.model = QLineEdit(cfg.llm_model)
        self.model.setPlaceholderText("The model's name on that server")
        form.addRow("Model", self.model)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.from_env = bool(os.environ.get(config.KEY_ENV))
        self.no_keyring = not self.from_env and not keychain.available()
        if self.from_env or self.no_keyring:
            self.key.setEnabled(False)
            self.key.setPlaceholderText(f"Taken from ${config.KEY_ENV}" if self.from_env
                                        else f"No keyring: set ${config.KEY_ENV}")
        else:
            if cfg.llm_url:
                self.key.setText(config.api_key(cfg.llm_url))
            self.key.setPlaceholderText("Only if the server needs one")
        form.addRow("API key", self.key)
        lay.addLayout(form)
        self.auto = QCheckBox("Summarize each recording when its transcript is ready")
        self.auto.setChecked(cfg.auto_summarize)
        self.auto.toggled.connect(self._update_warning)
        lay.addWidget(self.auto)
        self.titles = QCheckBox("Give recordings you did not name a short title from their summary")
        self.titles.setChecked(cfg.auto_title)
        lay.addWidget(self.titles)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        theme.set_role(self.warning, warn=True)
        lay.addWidget(self.warning)
        row = QHBoxLayout()
        self.test_btn = QPushButton("Test")
        self.test_btn.clicked.connect(self.test)
        row.addWidget(self.test_btn)
        self.result = _dim()
        row.addWidget(self.result, 1)
        lay.addLayout(row)
        lay.addWidget(_dim("The key is kept in your desktop's keyring (KDE Wallet, GNOME Keyring), "
                           "not in a file. To keep it elsewhere, set $" + config.KEY_ENV + " instead."))
        lay.addStretch(1)
        self._update_warning()

    def _config(self) -> config.Config:
        return config.Config(self.url.text().strip(), self.model.text().strip(), self.auto.isChecked(),
                             self.titles.isChecked(), auto_record=config.load().auto_record)

    def _update_warning(self):
        url = self.url.text().strip()
        remote = url and not config.is_local(url)
        what = ("Each transcript is sent to {} as soon as it is ready." if self.auto.isChecked()
                else "Transcripts you summarize are sent to {}.")
        self.warning.setText(what.format(config.host(url)) if remote else "")
        self.warning.setVisible(bool(remote))

    def test(self):
        cfg = self._config()
        if not cfg.llm_url:
            self.result.setText("Write the server's address first.")
            return
        self.result.setText("Asking the server…")
        self.test_btn.setEnabled(False)
        key = None if self.from_env or self.no_keyring else self.key.text().strip()

        def done(names):
            self.test_btn.setEnabled(True)
            if cfg.llm_model and names and cfg.llm_model not in names:
                self.result.setText(f"The server answers, but has no model “{cfg.llm_model}”. It has: "
                                    + ", ".join(names[:8]) + ("…" if len(names) > 8 else ""))
            else:
                self.result.setText("The server answers." + ("" if cfg.llm_model else " Now name a model."))

        def failed(msg):
            self.test_btn.setEnabled(True)
            self.result.setText(f"No answer: {msg}")

        run_task(lambda: llm.models(cfg, key=key), on_done=done, on_error=failed)

    def apply(self):
        cfg = self._config()
        if cfg.llm_url and not cfg.llm_url.startswith(("http://", "https://")):
            raise ValueError("the address starts with http:// or https://")
        if cfg.llm_url and not cfg.llm_model:
            raise ValueError("name the model to use on that server")
        if not (self.from_env or self.no_keyring) and cfg.llm_url:
            try:
                config.save_key(self.key.text(), cfg.llm_url)
            except keychain.KeychainError as e:
                raise ValueError(str(e)) from None
        config.save(cfg)
        if self.on_saved:
            self.on_saved()


class SummaryView(QWidget):
    """The selected recording's summary, with Summarize and Copy. Read-only: it is replaced, not edited."""

    def __init__(self, jobs, message=None, show_recording=None):
        super().__init__()
        self.message = message or (lambda _t: None)
        self.show_recording = show_recording or (lambda _rid, _at: None)
        self.rec = None
        self.linked = None
        self.jobs = jobs
        jobs.changed.connect(self._on_changed)
        jobs.progress.connect(self._on_progress)
        jobs.failed.connect(lambda _rid, msg: self.message(f"Summary failed: {msg}"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 10)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.status = QLabel()
        self.status.setFont(theme.display_font(0.85, QFont.Weight.Bold))
        self.status.setWordWrap(True)
        theme.set_role(self.status, dim=True)
        bar.addWidget(self.status, 1)
        self.summarize_btn = QToolButton()
        self.summarize_btn.setIcon(icon("transcribe"))
        self.summarize_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.summarize_btn.clicked.connect(self.summarize)
        # The arrow beside Summarize picks the kind of meeting: the template, kept as a tag.
        self.template_menu = QMenu(self.summarize_btn)
        self.template_menu.aboutToShow.connect(self._fill_templates)
        self.summarize_btn.setMenu(self.template_menu)
        self.summarize_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        bar.addWidget(self.summarize_btn)
        self.follow_btn = QToolButton()
        self.follow_btn.setText("Follow-up")
        self.follow_btn.setIcon(icon("mail"))
        self.follow_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.follow_btn.setToolTip("Draft the follow-up email from this summary")
        self.follow_btn.clicked.connect(self.follow_up)
        bar.addWidget(self.follow_btn)
        self.copy_btn = QToolButton()
        self.copy_btn.setText("Copy")
        self.copy_btn.setIcon(icon("copy"))
        self.copy_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_btn.setToolTip("Copy the summary as Markdown")
        self.copy_btn.clicked.connect(self.copy)
        bar.addWidget(self.copy_btn)
        lay.addLayout(bar)
        self.text = ReadingBrowser()  # in the reading card, read like the transcript
        self.text.setOpenExternalLinks(True)
        self.text.setAccessibleName("Summary")
        lay.addWidget(self.text, 1)
        # The summary's action items, to polish before they go to the team's tracker; their time
        # buttons play where each came up.
        self.actions_box = QWidget()
        al = QVBoxLayout(self.actions_box)
        al.setContentsMargins(0, 6, 0, 0)
        al.setSpacing(6)
        ah = QHBoxLayout()
        head = QLabel("Action items")
        head.setFont(theme.display_font(0.95, QFont.Weight.Bold))
        ah.addWidget(head)
        ah.addStretch(1)
        self.add_btn = QToolButton()
        self.add_btn.setText("Add")
        self.add_btn.setToolTip("Add an action item")
        self.add_btn.clicked.connect(lambda: self.actions.start_add())
        ah.addWidget(self.add_btn)
        al.addLayout(ah)
        self.actions = ActionList(editable=True)
        self.actions.play.connect(lambda rid, at: self.show_recording(rid, at))
        self.actions.relaid.connect(self._fit_actions)
        scroll = QScrollArea()
        # On the reading card's surface, not the window's.
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.actions)
        self.actions_scroll = scroll
        al.addWidget(scroll)
        lay.addWidget(self.actions_box)
        self.show_subject(None, None)

    def show_subject(self, rec, linked):
        self.rec, self.linked = rec, linked
        data = summary.load(rec) if rec is not None else None
        has_text = rec is not None and bool(rec.text().strip())
        job = self.jobs.state(rec.id) if rec is not None else None
        busy = job is not None
        failure = self.jobs.failure(rec.id) if rec is not None else None
        self.summarize_btn.setVisible(has_text and config.enabled())
        self.summarize_btn.setEnabled(not busy)
        self.summarize_btn.setText("Summarize again" if data else "Summarize")
        self.copy_btn.setVisible(data is not None)
        self.follow_btn.setVisible(data is not None and not busy)
        self.actions.set_recording(rec if data is not None else None)
        self.actions_box.setVisible(data is not None and not busy)
        self._fit_actions()
        if data is not None:
            self.text.show_markdown(data["text"])
        else:
            self.text.clear()
        if linked is not None:
            self.status.setText("Select one recording of the set to see or write its summary.")
        elif rec is None:
            self.status.setText("")
        elif job == "running":
            self.status.setText("Summarizing…")
        elif job == "queued":
            self.status.setText("Waiting to be summarized…")
        elif failure:
            self.status.setText(f"Summary failed: {failure}")
        elif data is not None:
            note = f"From {data.get('server') or 'the server'}"
            if data.get("template"):
                note += f" · {data['template']}"
            self.status.setText("The transcript changed since this summary." if summary.stale(rec, data) else note)
        elif not has_text:
            self.status.setText("Transcribe this recording to summarize it.")
        elif not config.enabled():
            self.status.setText("Set up a server in Settings, Summaries, to summarize.")
        else:
            self.status.setText("No summary yet.")
        if data is None and rec is not None:
            # Nothing to read yet: say it in the middle of the card, not only in the small status line.
            self.text.show_placeholder(self.status.text())
            self.status.setText("")  # said once; the label keeps its room so the buttons stay right

    def summarize(self):
        if self.rec is not None:
            self.jobs.request(self.rec.id)

    def follow_up(self):
        rec = self.rec
        if rec is None:
            return
        self.follow_btn.setEnabled(False)
        self.status.setText("Drafting the follow-up…")

        def done(result):
            self.follow_btn.setEnabled(True)
            self.show_subject(self.rec, self.linked)
            FollowUpDialog(*result, parent=self).show()

        def failed(msg):
            self.follow_btn.setEnabled(True)
            self.show_subject(self.rec, self.linked)
            self.message(f"No draft: {msg}")

        run_task(lambda: followup.draft(rec), on_done=done, on_error=failed)

    def _fit_actions(self):
        """As tall as the items (or the editor), up to a third of a typical card; more scroll."""
        self.actions.adjustSize()
        self.actions_scroll.setFixedHeight(min(ACTIONS_MAX_H, self.actions.sizeHint().height() + 4))

    def _fill_templates(self):
        m = self.template_menu
        m.clear()
        if self.rec is None:
            return
        m.addSection("Summarize as")
        group = QActionGroup(m)
        current, _ = templates.resolve(self.rec)
        for name in [None, *templates.names()]:
            a = m.addAction(name or "General meeting")
            a.setCheckable(True)
            a.setChecked(name == current if name else current is None)
            group.addAction(a)
            a.triggered.connect(lambda _c=False, n=name: self.use_template(n))

    def use_template(self, name: str | None):
        """Summarize again as this kind of meeting; the choice is kept as the recording's tag."""
        rec = self.rec
        if rec is None:
            return
        templates.set_for(rec, name)
        self.jobs.request(rec.id)

    def _on_changed(self, rid: str):
        if self.rec is not None and self.rec.id == rid:
            self.show_subject(self.rec, self.linked)

    def _on_progress(self, rid: str, done: int, total: int):
        if total > 1 and self.rec is not None and self.rec.id == rid:
            self.status.setText(f"Summarizing… part {done + 1} of {total}" if done + 1 < total
                                else "Summarizing… joining the parts")

    def copy(self):
        data = summary.load(self.rec) if self.rec is not None else None
        if data:
            QApplication.clipboard().setText(data["text"] + "\n")
            self.message("Summary copied.")


class FollowUpDialog(QDialog):
    """The drafted email, to edit, copy or open in the mail program. Studio sends nothing."""

    def __init__(self, subject: str, body: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Follow-up")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.subject = QLineEdit(subject)
        form.addRow("Subject", self.subject)
        lay.addLayout(form)
        self.body = QPlainTextEdit(body)
        self.body.setAccessibleName("Email")
        lay.addWidget(self.body, 1)
        row = QHBoxLayout()
        row.addWidget(_dim("Check it before sending: it was written by a language model."), 1)
        copy = QPushButton("Copy")
        copy.clicked.connect(self.copy)
        row.addWidget(copy)
        mail = QPushButton("Open in mail")
        mail.setDefault(True)
        mail.clicked.connect(self.open_mail)
        row.addWidget(mail)
        lay.addLayout(row)

    def copy(self):
        QApplication.clipboard().setText(f"{self.subject.text()}\n\n{self.body.toPlainText()}")

    def open_mail(self):
        QDesktopServices.openUrl(QUrl(followup.mailto(self.subject.text(), self.body.toPlainText())))

