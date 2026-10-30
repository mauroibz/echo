"""Small parts of the main window: the drop overlay, messages, the view switch, Space to play."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from . import motion, theme

log = logging.getLogger(__name__)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
        super().__init__("Drop audio or video to import", parent)
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


class Toast(QLabel):
    """A short message over the bottom of the content, gone after a few seconds."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(True)
        self.setMaximumWidth(560)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._timer = QTimer(self, singleShot=True, timeout=self._fade_out)
        self.hide()

    def show_text(self, text: str, ms: int | None = None):
        self.setText(text)
        self.adjustSize()
        self.place()
        if not self.isVisible():
            self.show()
            motion.fade(self, 1.0, motion.MEDIUM, start=0.0)
        self.raise_()
        self._timer.start(ms or (4000 if len(text) < 70 else 6500))

    def _fade_out(self):
        if motion.on():
            motion.fade(self, 0.0, motion.MEDIUM, done=lambda: (self.hide(), self.setGraphicsEffect(None)))
        else:
            self.hide()

    def place(self):
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 104)


class ViewSwitch(QWidget):
    """The transcript, and the views extensions add beside it, one shown at a time. With no
    added view there is no switch: the transcript card alone, as in Echo without extensions."""

    def __init__(self, transcript: QWidget):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.bar = QWidget()
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(16, 12, 16, 0)
        bl.setSpacing(4)
        bl.addStretch(1)
        self.bar.hide()
        lay.addWidget(self.bar)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.buttons: list[QToolButton] = []
        self._add_page("Transcript", transcript)
        self.buttons[0].setChecked(True)

    def _add_page(self, title: str, widget: QWidget):
        b = QToolButton()
        b.setText(title)
        b.setCheckable(True)
        b.setAutoExclusive(True)
        b.setAccessibleName(f"Show {title.lower()}")
        k = self.stack.addWidget(widget)
        b.clicked.connect(lambda: self.stack.setCurrentIndex(k))
        self.bar.layout().insertWidget(len(self.buttons), b)
        self.buttons.append(b)

    def add(self, title: str, widget: QWidget):
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._add_page(title, widget)
        self.bar.show()

    def views(self) -> list[QWidget]:
        return [self.stack.widget(i) for i in range(1, self.stack.count())]

    def show_subject(self, rec, linked):
        for w in self.views():
            fn = getattr(w, "show_subject", None)
            if fn is None:
                continue
            try:
                fn(rec, linked)
            except Exception:
                log.exception("view %s failed to show the selection", type(w).__name__)
