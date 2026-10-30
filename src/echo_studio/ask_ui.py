"""Questions in the window: an Ask view beside a recording's transcript, and an Ask screen for the
library. Answers cite where they come from; a citation plays the recording from there."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QTextBrowser, QToolButton, QVBoxLayout, QWidget

from echo_app import settings
from echo_app.index import Index
from echo_app.ui import theme
from echo_app.ui.common import icon, run_task

from . import ask


class Conversation(QWidget):
    """Questions and answers, newest last, with a box to ask. `answer(question, history)` runs off
    the window's thread and returns Markdown whose echo: links are citations."""

    def __init__(self, answer, show_recording, placeholder: str):
        super().__init__()
        self.answer = answer
        self.show_recording = show_recording
        self.turns: list[tuple[str, str, str]] = []  # question, answer as said, answer as shown
        self.busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self._open)
        self.text.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.text.setAccessibleName("Answers")
        lay.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.box = QLineEdit()
        self.box.setPlaceholderText(placeholder)
        self.box.setAccessibleName("Question")
        self.box.returnPressed.connect(self.ask)
        row.addWidget(self.box, 1)
        self.clear_btn = QToolButton()
        self.clear_btn.setIcon(icon("clear"))
        self.clear_btn.setToolTip("Start over")
        self.clear_btn.clicked.connect(self.clear)
        row.addWidget(self.clear_btn)
        lay.addLayout(row)
        self.status = QLabel()
        theme.set_role(self.status, dim=True)
        lay.addWidget(self.status)
        self._render()

    def clear(self):
        self.turns = []
        self._render()

    def ask(self):
        q = self.box.text().strip()
        if not q or self.busy:
            return
        self.busy = True
        self.box.setEnabled(False)
        self.status.setText("Thinking…")
        history = [(t[0], t[1]) for t in self.turns]

        def done(result):
            said, shown = result
            self.turns.append((q, said, shown))
            self._finish()
            self.box.clear()

        def failed(msg):
            self._finish()
            self.status.setText(f"No answer: {msg}")

        run_task(lambda: self.answer(q, history), on_done=done, on_error=failed)

    def _finish(self):
        self.busy = False
        self.box.setEnabled(True)
        self.box.setFocus()
        self.status.setText("")
        self._render()

    def _render(self):
        if not self.turns:
            self.text.setMarkdown("")
            return
        self.text.setMarkdown("\n\n---\n\n".join(f"**{q}**\n\n{shown}" for q, _said, shown in self.turns))
        bar = self.text.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _open(self, url: QUrl):
        target = ask.parse_link(url.toString())
        if target is not None:
            self.show_recording(*target)


class AskView(QWidget):
    """Beside the transcript: questions about the shown recording, kept while it is shown."""

    def __init__(self, show_recording):
        super().__init__()
        self.rec = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 10)
        self.hint = QLabel()
        theme.set_role(self.hint, dim=True)
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.chat = Conversation(self._answer, show_recording, "Ask about this recording…")
        lay.addWidget(self.chat, 1)
        self.show_subject(None, None)

    def _answer(self, question, history):
        rec = self.rec
        said = ask.ask_recording(rec, question, history)
        return said, ask.link_times(said, rec.id)

    def show_subject(self, rec, linked):
        if rec is None or self.rec is None or rec.id != self.rec.id:
            self.chat.clear()  # a conversation belongs to one recording
        self.rec = rec
        has_text = rec is not None and bool(rec.transcript())
        self.chat.setVisible(has_text and linked is None)
        if linked is not None:
            self.hint.setText("Select one recording of the set to ask about it.")
        elif rec is None:
            self.hint.setText("")
        elif not has_text:
            self.hint.setText("Transcribe this recording to ask about it.")
        else:
            self.hint.setText("Answers come from this recording's transcript; a time plays it from there.")


class AskScreen(QWidget):
    """Questions across the library: what was said where, with each citation opening its passage."""

    def __init__(self, library, show_recording):
        super().__init__()
        self.library = library
        self.setObjectName("content")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 24, 18)
        lay.setSpacing(10)
        title = QLabel("Ask")
        title.setFont(theme.display_font(1.6, QFont.Weight.Bold))
        lay.addWidget(title)
        hint = QLabel("Ask about anything said in your recordings, for example “what did we agree with Acme "
                      "about prices?”. The passages that match are sent to the server, and each answer "
                      "cites them.")
        hint.setWordWrap(True)
        theme.set_role(hint, dim=True)
        lay.addWidget(hint)
        self.chat = Conversation(self._answer, show_recording, "Ask your recordings…")
        lay.addWidget(self.chat, 1)

    def _answer(self, question, history):
        index = Index(self.library)
        try:
            index.sync()
            said, passages = ask.ask_library(index, question, history, language=settings.load()[0].language)
        finally:
            index.close()
        if not passages:
            return "", "Nothing in your recordings matches that."
        return said, ask.link_refs(said, passages)
