"""A linked set in the transcript: its parts one under the other, each under a fixed heading."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor

from .. import align
from ..library import READY, RECORDING, T_FAILED, T_QUEUED, T_RUNNING, TRANSCRIPT, Recording
from . import theme
from .common import fmt_date, fmt_duration
from .transcript_text import HEAD, LOCK, SEP, _plain, segment_offsets, shown_segments


class SetPart:
    """One part of a linked set as laid out in the editor."""

    def __init__(self, rec: Recording, timeline_part, heading: str, state: str | None):
        self.rec = rec
        self.tl = timeline_part  # sets.Part: offset and crop on the set's timeline
        self.heading = heading
        self.state = state  # why there is no text yet; None when the part has text to edit
        self.loaded = ""  # the text shown when loaded or last saved
        self.sig = None


class SetsMixin:
    """TranscriptPanel's linked sets: loading the parts, keeping their headings fixed while the
    bodies are edited, saving each part and aligning the set's passages."""

    # ---- a linked set ----
    def _leave_set(self):
        self.linked, self._parts, self._loaded_ids, self._fixed = None, [], [], []
        self.editor.edit_guard = self.editor.heading_at = None
        self.editor.setAcceptDrops(True)
        self._shown_signature = None
        self.close_find()
        self._replay.stop()
        self._audio_k, self._typing_paused = None, False
        self._offer([])
        self._loading = True
        self.editor.setPlainText("")
        self._loading = False
        for a in (self.act_retx, self.act_retx_base, self.lang_menu.menuAction(), self.act_speakers):
            a.setVisible(True)

    def set_linked(self, linked, parts: list[Recording]):
        """Show a linked set: its parts' transcripts one under the other, edited in place."""
        if self.linked is None or linked.id != self.linked.id:
            self.save()
            if self.linked is None:
                self.set_recording(None)
            else:
                self._leave_set()
            self.linked = linked
            self.editor.edit_guard = self._edit_allowed
            self.editor.heading_at = self._heading_at
            self.editor.setAcceptDrops(False)  # dragging text could carry it into another part
            for a in (self.act_retx, self.act_retx_base, self.lang_menu.menuAction(), self.act_speakers):
                a.setVisible(False)  # these act on one recording: select the part
        self.linked = linked
        self._set_parts = parts
        self.refresh()

    @staticmethod
    def _part_state(rec: Recording) -> str | None:
        if rec.meta.state == RECORDING:
            return "Recording in progress"
        if rec.meta.state != READY:
            return "Needs attention: select this part to repair it"
        if rec.is_edited() or rec.path(TRANSCRIPT).exists():
            return None
        st = rec.transcript_status()
        if st == T_RUNNING:
            # No percentage here: a changing line would rebuild the set's text every second (the
            # list shows the progress).
            return "Transcribing…"
        if st == T_QUEUED:
            return "Waiting to transcribe"
        if st == T_FAILED:
            return "Transcription failed: select this part to try again"
        return "Not transcribed yet: select this part to transcribe it"

    def _set_signature(self, parts: list[Recording]):
        return tuple((self._signature(r), self._part_state(r), r.meta.title, r.meta.speakers_off,
                      tuple(sorted(r.meta.speakers.items())), r.meta.crop_start, r.meta.crop_end) for r in parts)

    def _refresh_set(self):
        from .. import sets

        parts = [self.library.get(r.id) or r for r in self._set_parts]
        self._set_parts = parts
        self.stack.setCurrentWidget(self.page)
        self.notice.hide()
        sig = (self.linked.id, self._set_signature(parts))
        if sig == self._shown_signature:
            self._update_set_status()
            return
        if self._autosave.isActive():
            self.save()  # unsaved typing becomes the parts' edited text before anything reloads
            parts = [self.library.get(r.id) or r for r in parts]
            self._set_parts = parts
            sig = (self.linked.id, self._set_signature(parts))
        for r in parts:
            self._apply_dictionary(r)
        where = self._cursor_in_part()  # measured on the text as it is, before the parts change
        tl = sets.timeline(parts)
        self._parts = []
        for k, (r, part) in enumerate(zip(parts, tl)):
            length = f"  ·  {fmt_duration(part.length)}" if r.meta.duration else ""
            heading = f"{k + 1}  ·  {r.meta.title}  ·  {fmt_date(r.meta.created)}{length}"
            self._parts.append(SetPart(r, part, heading, self._part_state(r)))
        self._load_set_text(where)
        self._shown_signature = sig
        self._update_set_status()

    def _cursor_in_part(self) -> tuple[int, int] | None:
        """(part, offset in its text) of the cursor, to put it back after the text is rebuilt."""
        if not self._parts or self.editor.document().isEmpty():
            return None
        pos = self.editor.textCursor().position()
        for k, b in enumerate(self._bodies()):
            if b is not None and b[0] <= pos <= b[1]:
                return k, pos - b[0]
        return None

    def _load_set_text(self, where: tuple[int, int] | None = None):
        old_ids = getattr(self, "_loaded_ids", [])
        where_id = old_ids[where[0]] if where and where[0] < len(old_ids) else None
        scroll = self.editor.verticalScrollBar().value()
        lines: list[tuple[str, int]] = []  # (text, block state); body text may hold several lines
        for k, part in enumerate(self._parts):
            if k:
                lines.append(("", SEP))
            lines.append((part.heading, HEAD + k))
            if part.state is not None:
                lines.append((part.state, LOCK + k))
            else:
                part.loaded = _plain(part.rec.text().rstrip("\n"))
                lines.append((part.loaded, -1))
        self._fixed = [(st, t) for t, st in lines if st >= HEAD]
        self._loaded_ids = [p.rec.id for p in self._parts]
        self._loading = True
        doc = self.editor.document()
        doc.setUndoRedoEnabled(False)
        self.editor.setPlainText("\n".join(t for t, _s in lines))
        block = doc.begin()
        for text, state in lines:
            n = text.count("\n") + 1
            for _ in range(n):
                block.setUserState(state)
                block = block.next()
        t = theme.current()
        head_fmt = QTextCharFormat()
        head_fmt.setFontWeight(QFont.Weight.Bold)
        head_fmt.setForeground(QColor(t.accent_deep))
        lock_fmt = QTextCharFormat()
        lock_fmt.setFontItalic(True)
        lock_fmt.setForeground(QColor(t.muted))
        block = doc.begin()
        while block.isValid():
            st = block.userState()
            if HEAD <= st < SEP and block.length() > 1:
                c = QTextCursor(block)
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                c.setCharFormat(head_fmt if st < LOCK else lock_fmt)
            block = block.next()
        doc.setUndoRedoEnabled(True)
        self._loading = False
        # The cursor goes back into the same part at the same place in its text, whatever changed
        # above it (a part transcribed, retitled, reordered).
        pos = 0
        if where_id in self._loaded_ids:
            b = self._bodies()[self._loaded_ids.index(where_id)]
            if b is not None:
                pos = min(b[0] + where[1], b[1])
        c = self.editor.textCursor()
        c.setPosition(min(pos, doc.characterCount() - 1))
        self.editor.setTextCursor(c)
        self.editor.verticalScrollBar().setValue(scroll)
        self._corrections = []
        self._current_span = -1
        self._align_now()

    def _bodies(self) -> list[tuple[int, int] | None]:
        """Each part's editable text as (start, end) positions; None for a part without text."""
        doc = self.editor.document()
        out: list[tuple[int, int] | None] = [None] * len(self._parts)
        k, start, end = -1, None, None
        block = doc.begin()

        def close():
            if 0 <= k < len(out) and start is not None and self._parts[k].state is None:
                out[k] = (start, end)

        while block.isValid():
            st = block.userState()
            if HEAD <= st < LOCK:
                close()
                k, start, end = st - HEAD, None, None
            elif st >= LOCK:
                pass
            else:
                if start is None:
                    start = block.position()
                end = block.position() + block.length() - 1
            block = block.next()
        close()
        return out

    def _edit_allowed(self, lo: int, hi: int) -> bool:
        return any(b is not None and b[0] <= lo and hi <= b[1] for b in self._bodies())

    def _heading_at(self, pos: int) -> int | None:
        block = self.editor.document().findBlock(pos)
        st = block.userState()
        return st - HEAD if HEAD <= st < LOCK else None

    def _structure_ok(self) -> bool:
        """Every fixed line (heading, state line, blank line between parts) is there, unchanged."""
        fixed = []
        block = self.editor.document().begin()
        while block.isValid():
            if block.userState() >= HEAD:
                fixed.append((block.userState(), block.text()))
            block = block.next()
        return fixed == getattr(self, "_fixed", [])

    def _reassign_states(self):
        """After an undo, Qt recreates removed lines without their state: find them again. A
        heading is found by its text; its state line follows it, the blank line precedes it."""
        doc = self.editor.document()
        blocks = []
        block = doc.begin()
        while block.isValid():
            blocks.append(block)
            block = block.next()
        marked = {}
        i = 0
        for k, part in enumerate(self._parts):
            while i < len(blocks) and blocks[i].text() != part.heading:
                i += 1
            if i == len(blocks):
                return
            marked[i] = HEAD + k
            if k and i > 0 and blocks[i - 1].text() == "":
                marked[i - 1] = SEP
            if part.state is not None and i + 1 < len(blocks) and blocks[i + 1].text() == part.state:
                marked[i + 1] = LOCK + k
            i += 1
        for n, b in enumerate(blocks):
            b.setUserState(marked.get(n, -1))

    def _check_structure(self, _pos, _removed, _added):
        """The last guard: an edit that reached a heading anyway (an input method, a drop) is undone."""
        if self.linked is None or self._loading or self._structure_ok():
            return
        QTimer.singleShot(0, self._restore_structure)

    def _restore_structure(self):
        if self.linked is None or self._structure_ok():
            return
        self._loading = True
        self.editor.undo()
        self._reassign_states()
        self._loading = False
        if not self._structure_ok():
            # Not repairable in place: keep what can be kept before showing the files again.
            self._shown_signature = None
            self._refresh_set()
        self._align_now()
        self.message.emit("Each part's heading stays as it is; edit the text under it.")

    def _part_text(self, k: int, bodies=None) -> str | None:
        bodies = self._bodies() if bodies is None else bodies
        b = bodies[k]
        if b is None:
            return None
        c = QTextCursor(self.editor.document())
        c.setPosition(b[0])
        c.setPosition(b[1], QTextCursor.MoveMode.KeepAnchor)
        return c.selection().toPlainText()

    def _save_set(self):
        if not self._structure_ok():
            self.message.emit("Not saved: a part's heading changed. The text is shown again as saved.")
            self._shown_signature = None
            self._refresh_set()
            return
        bodies = self._bodies()
        for k, part in enumerate(self._parts):
            text = self._part_text(k, bodies)
            if text is None or text == part.loaded:
                continue
            rec = part.rec
            try:
                if text == _plain(rec.base_text().rstrip("\n")):
                    if rec.is_edited():
                        rec.revert_edits()
                else:
                    rec.save_edited(text)
            except OSError as e:
                self.message.emit(f"Could not save your edits: {e}")
                return
            part.loaded = text
            self.changed.emit(rec.id)
            if rec.is_edited():
                self._learn_from(rec, text)
        self._shown_signature = (self.linked.id, self._set_signature([p.rec for p in self._parts]))
        self._update_set_status()

    def _update_set_status(self):
        edited = sum(1 for p in self._parts if p.rec.is_edited())
        waiting = sum(1 for p in self._parts if p.state is not None)
        bits = [f"{len(self._parts)} parts"]
        if edited:
            bits.append(f"{edited} edited")
        if waiting:
            bits.append(f"{waiting} without text yet")
        self.status.setText(" · ".join(bits))
        self.act_revert.setEnabled(False)
        self._update_flag_count()

    def _set_segments(self) -> list[dict]:
        """Every part's shown segments on the set's timeline, each knowing its part."""
        out = []
        for k, part in enumerate(self._parts):
            if part.state is not None:
                continue
            for sg in shown_segments(part.rec):
                out.append({**sg, "start": part.tl.to_set(float(sg.get("start", 0.0))),
                            "end": part.tl.to_set(float(sg.get("end", 0.0))), "_part": k})
        return out

    def _align_set(self):
        """Passage spans of every part, in document positions and set time."""
        text = self.editor.toPlainText()
        bodies = self._bodies()
        segs = self._set_segments()
        self._segments = segs
        passages, corrections = [], []
        self._correction_part = {}
        for k, part in enumerate(self._parts):
            b = bodies[k]
            if b is None:
                continue
            idx = [i for i, sg in enumerate(segs) if sg["_part"] == k]
            local = [segs[i] for i in idx]
            language = (part.rec.transcript() or {}).get("language", "es")
            body = text[b[0]:b[1]]
            if local:
                passages += [(b[0] + a, b[0] + e, idx[j]) for a, e, j in align.align(local, body, language) if e > a]
            if not part.rec.is_edited() and body == part.loaded:
                c = part.rec.corrected()
                if c:
                    offsets = segment_offsets(local, language)
                    for ed in c.get("edits", []):
                        base = offsets.get(ed.get("segment"))
                        if base is not None:
                            corrections.append((b[0] + base + ed["start"], b[0] + base + ed["end"], ed))
                            self._correction_part[id(ed)] = part.rec
        self._passages = passages
        self._pieces = []  # speaker fixes are made on a part, not in the set
        self._spans = [(a, e, float(segs[k].get("start", 0.0))) for a, e, k in passages]
        self._flagged = [(a, e, segs[k]) for a, e, k in passages
                         if segs[k].get("flags") and text[a:e].strip() == (segs[k].get("text") or "").strip()]
        self._corrections = corrections
        self._update_margin()
        self._apply_selections()
        self._update_flag_count()
