"""Finding in the transcript: the find bar, searches carried from the library, a speaker search."""

from __future__ import annotations

from PySide6.QtGui import QTextCursor


from .transcript_text import _fold, _occurrences


class FindMixin:
    """TranscriptPanel's find bar. Expects the panel's editor, find widgets and passages."""

    # ---- find ----
    def open_find(self):
        if self.stack.currentWidget() is not self.page:
            return
        self.findbar.show()
        self._find_from_search = False
        sel = self.editor.textCursor().selectedText()
        if sel and " " not in sel:
            self.find_edit.setText(sel)
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        self._find_update()

    def find_from_search(self, text: str, speakers=None):
        """Show the find bar with the library search's words, leaving the focus where it is
        (the list, while the user steps through results). With `speakers` (numbers), only their
        passages are searched: what @Ana said, not what anyone said."""
        if self.stack.currentWidget() is not self.page:
            return
        self._find_speakers = set(speakers) if speakers and self.linked is None else None
        self.findbar.show()
        self._find_from_search = True
        cur = self.editor.textCursor()
        cur.setPosition(0)  # from the first occurrence, as a newly opened result
        self.editor.setTextCursor(cur)
        if self.find_edit.text() == text:
            self._find_update()
        else:
            self.find_edit.setText(text)  # runs _find_update

    def search_cleared(self):
        """The library search was cleared: its find bar goes too, one the user opened stays."""
        if self._find_from_search and self.findbar.isVisible():
            self.close_find(focus=False)

    def close_find(self, focus: bool = True):
        self._find_from_search = False
        self._find_speakers = None
        self.findbar.hide()
        self._find_matches = []
        self._apply_selections()
        if focus and self.stack.currentWidget() is self.page:
            self.editor.setFocus()

    def _find_update(self):
        q = _fold(self.find_edit.text())
        self._find_matches = []
        if q:
            hay = _fold(self.editor.toPlainText())
            self._find_matches = _occurrences(hay, q)
            if not self._find_matches and len(q.split()) > 1:
                # The library search matches the words anywhere, so a search carried over from it
                # (or typed here) that is not a phrase in this text finds each word instead.
                spans = sorted(m for w in set(q.split()) for m in _occurrences(hay, w))
                for a, b in spans:
                    if not self._find_matches or a >= self._find_matches[-1][1]:
                        self._find_matches.append((a, b))
            if self._find_speakers:
                self._find_matches = [m for m in self._find_matches if self._speaker_at(m[0]) in self._find_speakers]
        self._find_index = -1
        self._find_step(1)

    def _find_typed(self, _text: str):
        """Typed here, the find is the user's own: all speakers, and no longer the library search's."""
        self._find_from_search = False
        if self._find_speakers:
            self._find_speakers = None
            self._find_update()

    def _speaker_at(self, pos: int) -> int | None:
        k = self._passage_at(pos)
        if k is None or k >= len(self._passages):
            return None
        piece = self._piece_at(pos)
        n = piece[3] if piece else self._segments[self._passages[k][2]].get("speaker")
        return self.rec.speaker(n) if self.rec is not None else n

    def _piece_at(self, pos: int):
        """The speaker piece (start, end, segment, speaker) at a text position, or the one before it."""
        best = None
        for p in self._pieces:
            if p[0] <= pos:
                best = p
            else:
                break
        return best

    def _find_step(self, direction: int):
        n = len(self._find_matches)
        if not n:
            self.find_count.setText("No matches" if self.find_edit.text() else "")
            self._apply_selections()
            return
        pos = self.editor.textCursor().selectionStart() if self._find_index < 0 else None
        if pos is not None and direction > 0:
            self._find_index = next((k for k, (a, _) in enumerate(self._find_matches) if a >= pos), 0)
        else:
            self._find_index = (self._find_index + direction) % n
        a, b = self._find_matches[self._find_index]
        cur = self.editor.textCursor()
        cur.setPosition(a)
        cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cur)
        self.editor.ensureCursorVisible()
        self.find_count.setText(f"{self._find_index + 1} of {n}")
        self._apply_selections()
