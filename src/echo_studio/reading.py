"""Studio's text as the transcript reads: the same face, column width and quiet headings."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontInfo, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QFrame, QTextBrowser

from echo_app.ui import theme

MAX_TEXT_WIDTH_CHARS = 90  # as the transcript's column
HEADING_SCALE = {1: 1.3, 2: 1.12, 3: 1.04}  # Markdown's defaults (2x for #) shout over the text


class ReadingBrowser(QTextBrowser):
    """Read-only Markdown in the reading face, centred in a column no wider than the transcript's."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFont(theme.reading_font())
        self.document().setDocumentMargin(14)
        self.document().setIndentWidth(18)  # bullets close to the heading they belong to

    def show_markdown(self, text: str) -> None:
        self.setMarkdown(text)
        self._tune()

    def _tune(self):
        """Headings a step above the text, bold, with room above; list items and paragraphs spaced
        like the transcript's paragraphs."""
        self.ensurePolished()  # the style sheet's font size arrives with polishing
        doc = self.document()
        base = QFontInfo(self.font()).pointSizeF()  # the set size can be in pixels (-1 in points)
        cur = QTextCursor(doc)
        block = doc.begin()
        first = True
        while block.isValid():
            level = block.blockFormat().headingLevel()
            cur.setPosition(block.position())
            cur.setPosition(block.position() + max(0, block.length() - 1), QTextCursor.MoveMode.KeepAnchor)
            bf = QTextBlockFormat(block.blockFormat())
            if level:
                # Replaced, not merged: Markdown's heading format sizes the text in pixels, which
                # would win over a size in points.
                cf = QTextCharFormat()
                cf.setFontPointSize(base * HEADING_SCALE.get(level, 1.0))
                cf.setFontWeight(QFont.Weight.Bold)
                cf.setFontFamilies(theme.display_font().families())
                cur.setCharFormat(cf)
                bf.setTopMargin(0 if first else base * 1.4)
                bf.setBottomMargin(base * 0.35)
            else:
                bf.setTopMargin(base * 0.15)
                bf.setBottomMargin(base * 0.15)
                bf.setLineHeight(135, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            cur.setBlockFormat(bf)
            first = False
            block = block.next()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # A reading column: side margins once the view is wider than the column.
        col = self.fontMetrics().averageCharWidth() * MAX_TEXT_WIDTH_CHARS + 60  # as the transcript's
        side = max(0, (self.width() - col) // 2)
        self.setViewportMargins(side, 0, side, 0)
