"""Studio in the window: the Summaries settings page and the Summary view beside the transcript."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from echo_app.ui import theme
from echo_app.ui.common import icon, run_task

from . import config, llm, summary

VIEW_TITLE = "Summary"


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
                           "computer (llama.cpp, Ollama, vLLM) or a cloud provider with an OpenAI-compatible "
                           "API. Leave the address empty to turn them off."))
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
        if self.from_env:
            self.key.setEnabled(False)
            self.key.setPlaceholderText(f"Taken from ${config.KEY_ENV}")
        else:
            self.key.setText(config.api_key())
            self.key.setPlaceholderText("Only if the server needs one")
        form.addRow("API key", self.key)
        lay.addLayout(form)
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
        lay.addWidget(_dim(f"The key is kept in {config.key_path()}, readable only by you."))
        lay.addStretch(1)
        self._update_warning()

    def _config(self) -> config.Config:
        return config.Config(self.url.text().strip(), self.model.text().strip())

    def _update_warning(self):
        url = self.url.text().strip()
        remote = url and not config.is_local(url)
        self.warning.setText(f"Transcripts you summarize are sent to {config.host(url)}." if remote else "")
        self.warning.setVisible(bool(remote))

    def test(self):
        cfg = self._config()
        if not cfg.llm_url:
            self.result.setText("Write the server's address first.")
            return
        self.result.setText("Asking the server…")
        self.test_btn.setEnabled(False)
        key = None if self.from_env else self.key.text().strip()

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
        config.save(cfg)
        if not self.from_env:
            config.save_key(self.key.text())
        if self.on_saved:
            self.on_saved()


class SummaryView(QWidget):
    """The selected recording's summary, with Summarize and Copy. Read-only: it is replaced, not edited."""

    def __init__(self, message=None):
        super().__init__()
        self.message = message or (lambda _t: None)
        self.rec = None
        self._busy: set[str] = set()
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
        bar.addWidget(self.summarize_btn)
        self.copy_btn = QToolButton()
        self.copy_btn.setText("Copy")
        self.copy_btn.setIcon(icon("copy"))
        self.copy_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_btn.setToolTip("Copy the summary as Markdown")
        self.copy_btn.clicked.connect(self.copy)
        bar.addWidget(self.copy_btn)
        lay.addLayout(bar)
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        self.text.setAccessibleName("Summary")
        self.text.setFrameShape(QFrame.Shape.NoFrame)  # it sits in the reading card, like the transcript
        lay.addWidget(self.text, 1)
        self.show_subject(None, None)

    def show_subject(self, rec, linked):
        self.rec = rec
        data = summary.load(rec) if rec is not None else None
        has_text = rec is not None and bool(rec.text().strip())
        busy = rec is not None and rec.id in self._busy
        self.summarize_btn.setVisible(has_text and config.enabled())
        self.summarize_btn.setEnabled(not busy)
        self.summarize_btn.setText("Summarize again" if data else "Summarize")
        self.copy_btn.setVisible(data is not None)
        if data is not None:
            self.text.setMarkdown(data["text"])
        else:
            self.text.clear()
        if linked is not None:
            self.status.setText("Select one recording of the set to see or write its summary.")
        elif rec is None:
            self.status.setText("")
        elif busy:
            self.status.setText("Summarizing…")
        elif data is not None:
            note = f"From {data.get('server') or 'the server'}"
            self.status.setText("The transcript changed since this summary." if summary.stale(rec, data) else note)
        elif not has_text:
            self.status.setText("Transcribe this recording to summarize it.")
        elif not config.enabled():
            self.status.setText("Set up a server in Settings, Summaries, to summarize.")
        else:
            self.status.setText("No summary yet.")

    def summarize(self):
        rec = self.rec
        if rec is None or rec.id in self._busy:
            return
        self._busy.add(rec.id)
        self.show_subject(rec, None)

        def work(progress):
            return summary.write(rec, progress=lambda d, t: progress((d, t)))

        def on_progress(v):
            done, total = v
            if total > 1 and self.rec is not None and self.rec.id == rec.id:
                self.status.setText(f"Summarizing… part {done + 1} of {total}" if done + 1 < total
                                    else "Summarizing… joining the parts")

        def finished(_data=None):
            self._busy.discard(rec.id)
            if self.rec is not None and self.rec.id == rec.id:
                self.show_subject(self.rec, None)

        def failed(msg):
            finished()
            self.message(f"Summary failed: {msg}")
            if self.rec is not None and self.rec.id == rec.id:
                self.status.setText(f"Summary failed: {msg}")

        run_task(work, on_done=finished, on_error=failed, on_progress=on_progress)

    def copy(self):
        data = summary.load(self.rec) if self.rec is not None else None
        if data:
            QApplication.clipboard().setText(data["text"] + "\n")
            self.message("Summary copied.")
