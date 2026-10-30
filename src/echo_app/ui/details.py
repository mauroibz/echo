"""Details: what belongs to the selected recording but need not be on screen all the time."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .. import export
from . import theme


class DetailsPanel(QScrollArea):
    """A card at the right of the transcript: notes, markers, the context line, the file, the
    statistics and how the transcript was made. The widgets are the player's and the
    transcript's own; this panel only places them under headings and hides empty sections."""

    seek_requested = Signal(float)

    def __init__(self, player, transcript, parent=None):
        super().__init__(parent)
        self.player = player
        self.transcript = transcript
        self.setObjectName("details")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedWidth(300)
        body = QWidget()
        body.setObjectName("detailsbody")
        self.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(22, 20, 20, 20)
        lay.setSpacing(18)
        title = QLabel("Details")
        title.setFont(theme.display_font(1.1, QFont.Weight.ExtraBold))
        lay.addWidget(title)
        self.markers = QWidget()
        self._marker_layout = QVBoxLayout(self.markers)
        self._marker_layout.setContentsMargins(0, 0, 0, 0)
        self._marker_layout.setSpacing(2)
        self._marker_sig = None
        for w in (player.file_info, player.stats, transcript.status):
            w.setWordWrap(True)
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        theme.set_role(transcript.status, dim=False)
        transcript.status.setFont(player.stats.font())
        transcript.status.setStyleSheet("font-weight: 400;")  # it was a bold caption over the text
        player.notes.set_rest_lines(5)
        self.sections: list[tuple[QWidget, QWidget, bool]] = []  # section, content, hide when it has no text
        for head, w, textual in (("Notes", player.notes, False), ("Markers", self.markers, False),
                                 ("Context for transcription", player.context, False),
                                 ("Transcript", transcript.status, True), ("File", player.file_info, True),
                                 ("Statistics", player.stats, True)):
            sec = QWidget()
            sl = QVBoxLayout(sec)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.setSpacing(6)
            label = QLabel(head.upper())
            label.setFont(theme.display_font(0.76, QFont.Weight.ExtraBold))
            theme.set_role(label, eyebrow=True)
            sl.addWidget(label)
            sl.addWidget(w)
            lay.addWidget(sec)
            self.sections.append((sec, w, textual))
        lay.addStretch(1)

    def refresh(self):
        """Follow what the player shows: its markers, and which sections have anything."""
        self._show_markers(self.player.wave.markers if self.player.wave.isEnabled() else [])
        tp = self.transcript
        for sec, w, textual in self.sections:
            empty = textual and not w.text().strip()
            if w is tp.status and tp.stack.currentWidget() is not tp.page:
                empty = True  # the status of a transcript that is not shown: none yet, or one being made
            sec.setVisible(not w.isHidden() and not empty and (self.player.rec is not None
                                                               or self.player.linked is not None))

    def _show_markers(self, markers: list[dict]):
        sig = [(m.get("at"), m.get("note")) for m in markers]
        if sig == self._marker_sig:
            return
        self._marker_sig = sig
        while self._marker_layout.count():
            item = self._marker_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not markers:
            hint = QLabel("None. Press M while recording, or Ctrl+M while playing.")
            hint.setWordWrap(True)
            theme.set_role(hint, dim=True)
            self._marker_layout.addWidget(hint)
            return
        for m in markers:
            b = QPushButton()
            b.setObjectName("markerrow")
            b.setFlat(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            at = float(m.get("at") or 0)
            note = m.get("note") or "Marker"
            b.setText(f"{export.stamp(at)}   {note}")
            b.setToolTip("Play from here")
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _c=False, t=at: self.seek_requested.emit(t))
            self._marker_layout.addWidget(b)
