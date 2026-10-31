"""Who said what in the transcript: naming speakers, their names over turns, merging, Said by."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtWidgets import QCompleter, QMenu

from .. import align, dictionary, relabel, settings
from ..library import Recording
from .common import icon
from .transcript_text import NAME_SAMPLE_S, _html, shown_segments


log = logging.getLogger(__name__)


class SpeakersMixin:
    """TranscriptPanel's speakers: the naming bar, names and colors, merging and separating,
    voices, and fixing who said a passage. Expects the panel's recording, editor and pieces."""

    # ---- the naming bar ----
    def _unnamed_speaker(self) -> int | None:
        """The unnamed speaker with the most speech in the shown recording, if the bar should ask."""
        rec = self.rec
        if self.linked is not None or rec is None or rec.meta.speakers_off or rec.meta.naming_dismissed:
            return None
        t = rec.transcript() or {}
        info = t.get("speakers") or {}
        if not info:
            return None
        secs: dict[int, float] = {}
        fixes = rec.fixes(t)
        for k, sg in enumerate(t.get("segments") or []):
            n = rec.speaker_at(k, sg, fixes)
            if n is not None and sg.get("text"):
                secs[n] = secs.get(n, 0.0) + float(sg.get("end", 0)) - float(sg.get("start", 0))
        named = rec.meta.speakers
        waiting = [n for n in secs if str(n) not in named and n != info.get("me")]
        return max(waiting, key=lambda n: (secs[n], -n)) if waiting else None

    def _update_namebar(self):
        n = self._unnamed_speaker() if self.chip.isHidden() else None
        if n != self._ask:
            self._ask_typing = self._ask_your_name = False
            self.name_edit.clear()
        self._ask = n
        if n is None:
            self.namebar.hide()
            return
        rec = self.rec
        info = (rec.transcript() or {}).get("speakers") or {}
        your_name = settings.load()[0].your_name.strip()
        suggested = (info.get("suggested") or {}).get(str(n))
        if suggested and (suggested == your_name or suggested in rec.meta.speakers.values()):
            suggested = None  # already someone else in this recording
        me_named = info.get("me") is not None or (your_name and your_name in rec.meta.speakers.values())
        typing = self._ask_your_name or self._ask_typing or not suggested
        if self._ask_your_name:
            self.name_text.setText("What is your name? Echo will name you by itself from now on.")
            self.name_edit.setPlaceholderText("Your name")
        elif suggested and not self._ask_typing:
            self.name_text.setText(f"Speaker {n} sounds like <b>{_html(suggested)}</b>.")
            self.name_yes.setText(f"Yes, {suggested}")
        else:
            self.name_text.setText(f"Who is speaker {n}?")
            self.name_edit.setPlaceholderText("Name")
            people = [e.name for e in dictionary.current().entries if e.kind == dictionary.PEOPLE]
            completer = QCompleter(people, self.name_edit)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self.name_edit.setCompleter(completer)
        self.name_edit.setVisible(typing)
        self.name_yes.setVisible(not typing)
        self.name_other.setVisible(bool(suggested) and not typing)
        self.name_me.setVisible(not me_named and not self._ask_your_name)
        self.name_play.setVisible(self.player is not None)
        self.namebar.show()

    def _play_speaker(self):
        """A few seconds of the asked speaker: the start of their longest passage."""
        if self.player is None or self._ask is None or self.rec is None:
            return
        segs = [s for k, s in enumerate((self.rec.transcript() or {}).get("segments") or [])
                if self.rec.speaker_at(k, s) == self._ask and s.get("text")]
        if not segs:
            return
        sg = max(segs, key=lambda s: float(s.get("end", 0)) - float(s.get("start", 0)))
        start = float(sg.get("start", 0))
        self._audio_k, self._typing_paused = None, False
        self.player.play_span(start, min(float(sg.get("end", 0)), start + NAME_SAMPLE_S))
        self.player.seek_shown(start)  # the playhead and the text go there at once, not on the next tick
        self.follow(start, jump=True)

    def _name_suggested(self):
        info = ((self.rec.transcript() or {}).get("speakers") or {}) if self.rec else {}
        name = (info.get("suggested") or {}).get(str(self._ask))
        if self._ask is not None and name:
            self.name_speaker(self._ask, name)

    def _name_someone_else(self):
        self._ask_typing = True
        self._update_namebar()
        self.name_edit.setFocus()

    def _name_typed(self):
        name = " ".join(self.name_edit.text().split())
        if self._ask is None or not name:
            return
        if self._ask_your_name:
            cfg, _ = settings.load()
            cfg.your_name = name
            settings.save(cfg)
        self.name_edit.clear()
        self.name_speaker(self._ask, name)

    def _name_me(self):
        your_name = settings.load()[0].your_name.strip()
        if self._ask is None:
            return
        if your_name:
            self.name_speaker(self._ask, your_name)
            return
        self._ask_your_name = True
        self._update_namebar()
        self.name_edit.setFocus()

    def _name_dismiss(self):
        rec = self.rec
        if rec is None:
            return
        rec.update(naming_dismissed=True)
        self._update_namebar()
        self.changed.emit(rec.id)

    SPEAKER_COLORS = ("accent_deep", "orange", "violet", "coral_deep", "muted")

    def _speaker_labels(self) -> list[tuple[int, str, str, int]]:
        """A name where the speaker changes: the user's, a suggestion with "?", or "Speaker N"."""
        if self.linked is not None:
            return self._set_speaker_labels()
        rec = self.rec
        if rec is None or rec.meta.speakers_off:
            return []
        info = (rec.transcript() or {}).get("speakers") or {}
        if not info:
            return []
        suggested = info.get("suggested") or {}
        out, last = [], None
        for a, _b, _k, who in self._pieces:
            n = rec.speaker(who)  # the user's fixes are in the pieces; merged speakers are one
            if n is None or n == last:
                continue
            last = n
            name = rec.meta.speakers.get(str(n)) or (f"{suggested[str(n)]}?" if str(n) in suggested else f"Speaker {n}")
            out.append((a, name, self.SPEAKER_COLORS[(n - 1) % len(self.SPEAKER_COLORS)], n))
        return out

    def _set_speaker_labels(self) -> list[tuple[int, str, str, int]]:
        """Speaker names across a set's parts (naming them is done on the part); a part starts afresh."""
        out, last = [], None
        for a, _b, k in self._passages:
            sg = self._segments[k]
            rec = self._parts[sg["_part"]].rec
            info = (rec.transcript() or {}).get("speakers") or {}
            n = rec.speaker(sg.get("speaker"))
            key = (sg["_part"], n)
            if rec.meta.speakers_off or not info or n is None or key == last:
                continue
            last = key
            suggested = info.get("suggested") or {}
            name = rec.meta.speakers.get(str(n)) or (f"{suggested[str(n)]}?" if str(n) in suggested else f"Speaker {n}")
            out.append((a, name, self.SPEAKER_COLORS[(n - 1) % len(self.SPEAKER_COLORS)], n))
        return out

    def _speaker_menu(self, n: int, pos):
        if self.linked is not None:
            self.message.emit("Name speakers on the part: click its heading.")
            return
        rec = self.rec
        if rec is None:
            return
        info = (rec.transcript() or {}).get("speakers") or {}
        suggested = (info.get("suggested") or {}).get(str(n))
        current = rec.meta.speakers.get(str(n))
        m = QMenu(self)
        if suggested and not current:
            m.addAction(icon("ok"), f"Yes, this is {suggested}", lambda: self.name_speaker(n, suggested))
        m.addAction(icon("rename"), f"Name speaker {n}…" if not current else f"Rename {current}…",
                    lambda: self._ask_speaker_name(n))
        if current:
            m.addAction(icon("users"), f"Open {current}'s profile", lambda: self.profile_requested.emit(current))
            m.addAction(icon("clear"), "Forget this name", lambda: self.name_speaker(n, ""))
        others = [o for o in self._speakers_shown() if o != n]
        if others:
            same = m.addMenu(icon("link"), "Same person as")
            same.setToolTip("Speaker labeling found one person twice: make them one speaker in this recording")
            for o in others:
                same.addAction(self._speaker_title(rec, o), lambda o=o: self.merge_speaker(n, o))
        if rec.merged_into(n):
            m.addAction(icon("unlink"), "Separate again", lambda: self.separate_speaker(n))
        if relabel.relabeled(rec):
            m.addAction(icon("revert"), "Back to the speakers Echo found", self.restore_speakers)
        m.addSeparator()
        m.addAction(icon("users"), "No speaker labels for this recording", lambda: self.set_speakers_off(True))
        m.exec(pos)

    def _speakers_shown(self) -> list[int]:
        """The shown recording's speakers after fixes and merges, in order of first appearance."""
        rec = self.rec
        out: list[int] = []
        for *_x, who in (self._pieces if rec else []):
            n = rec.speaker(who)
            if n is not None and n not in out:
                out.append(n)
        return out

    @staticmethod
    def _speaker_title(rec: Recording, n: int) -> str:
        name = rec.meta.speakers.get(str(n))
        return f"{name} (speaker {n})" if name else f"Speaker {n}"

    def merge_speaker(self, source: int, target: int):
        """The user says `source` is `target`: one speaker in this recording from now on."""
        rec = self.rec
        if rec is None:
            return
        gone = rec.meta.speakers.get(str(rec.speaker(source)))
        rec.merge_speakers(source, target)
        name = rec.meta.speakers.get(str(rec.speaker(target)))
        if gone and gone != name:
            self._forget_voice(rec, gone)  # it was someone else's voice: not theirs after all
        if name:
            self._remember_voice(rec, rec.speaker(target), name)
        self.message.emit(f"Speaker {source} is now {name or f'speaker {target}'}. "
                          "“Separate again” on the name undoes it.")
        self._update_margin()
        self._update_status(rec)
        self.changed.emit(rec.id)

    def separate_speaker(self, n: int):
        rec = self.rec
        if rec is None:
            return
        parts = rec.separate_speakers(n)
        name = rec.meta.speakers.get(str(n))
        if name:
            self._remember_voice(rec, n, name)  # without the parts that are someone else
        self.message.emit("Separated speaker " + ", ".join(str(p) for p in parts) + ".")
        self._update_margin()
        self._update_status(rec)
        self.changed.emit(rec.id)

    @staticmethod
    def _remember_voice(rec: Recording, n: int, name: str):
        """This recording's part of the person's voice: the average of every speaker they are in it
        (`n`, others with the same name, and what was merged into them). It replaces the part an
        earlier naming of this recording gave."""
        centroids = (((rec.transcript() or {}).get("speakers") or {}).get("centroids") or {})
        same = {n} | {int(k) for k, v in rec.meta.speakers.items() if v == name}
        nums = [k for m in sorted(same) for k in [m, *rec.merged_into(m)]]
        parts = [centroids[str(k)] for k in nums if centroids.get(str(k))]
        if not parts:
            return
        mean = [sum(v) / len(parts) for v in zip(*parts)]
        person = dictionary.current().find(name)
        dictionary.remember_voice(person.name if person else name, mean, rec.id)

    @staticmethod
    def _forget_voice(rec: Recording, name: str):
        """`name` is no longer anyone in this recording: what it taught their voice is taken back."""
        if name in rec.meta.speakers.values():
            return
        person = dictionary.current().find(name)
        dictionary.forget_voice_part(person.name if person else name, rec.id)

    def _ask_speaker_name(self, n: int):
        from PySide6.QtWidgets import QInputDialog

        people = [e.name for e in dictionary.current().entries if e.kind == dictionary.PEOPLE]
        current = self.rec.meta.speakers.get(str(n), "") if self.rec else ""
        name, ok = QInputDialog.getItem(self, "Name the speaker", f"Who is speaker {n}?",
                                        ([current] if current else []) + [p for p in people if p != current],
                                        0, True)
        if ok:
            self.name_speaker(n, name.strip())

    def name_speaker(self, n: int, name: str):
        """Name a speaker for the whole recording. A name also becomes a person in the dictionary,
        whose voice is remembered so later recordings suggest it."""
        rec = self.rec
        if rec is None:
            return
        names = dict(rec.meta.speakers)
        before = names.get(str(n))
        if name:
            names[str(n)] = name
            if dictionary.current().find(name) is None and \
                    not self._dict_update(lambda d: d.add(dictionary.PEOPLE, name)):
                return
            self._remember_voice(rec, n, name)
        else:
            names.pop(str(n), None)
        rec.update(speakers=names)
        if before and before != name:
            self._forget_voice(rec, before)
        self._update_margin()
        self.changed.emit(rec.id)

    def set_speakers_off(self, off: bool):
        rec = self.rec
        if rec is None or rec.meta.speakers_off == off:
            return
        rec.update(speakers_off=off)
        self.act_speakers.setChecked(not off)
        self._update_margin()
        self.changed.emit(rec.id)
        if not off and not (rec.transcript() or {}).get("speakers"):
            self.message.emit("Transcribe again to label the speakers of this recording.")

    # ---- correcting who said what ----
    def _speaker_menu_items(self, menu, pos: int):
        """Said by, undoing a fix and joining paragraphs, at the top of the editor's menu."""
        rec = self.rec
        if self.linked is not None or rec is None or rec.meta.speakers_off \
                or not (rec.transcript() or {}).get("speakers"):
            return
        self._align_now()
        if not self._pieces:
            return
        cur = self.editor.textCursor()
        sel = (cur.selectionStart(), cur.selectionEnd()) if cur.hasSelection() else None
        if sel and not sel[0] <= pos <= sel[1]:
            sel = None  # the click was outside the selection: the paragraph under it
        first = menu.actions()[0] if menu.actions() else None
        said = QMenu("Said by", menu)
        said.setIcon(icon("users"))
        said.setToolTip("Who said the selected words, or this paragraph")
        for n in self._speakers_shown():
            said.addAction(self._speaker_title(rec, n), lambda n=n: self.said_by(n, sel, pos))
        said.addSeparator()
        said.addAction("Someone else…", lambda: self._said_by_someone_else(sel, pos))
        menu.insertMenu(first, said)
        if self._fix_at(pos) is not None:
            act = QAction(icon("revert"), "Back to the speaker Echo found", menu)
            act.triggered.connect(lambda: self.unfix_at(pos))
            menu.insertAction(first, act)
        if self._break_before(pos) is not None:
            act = QAction(icon("collapse"), "Join with the paragraph above", menu)
            act.triggered.connect(lambda: self.join_above(pos))
            menu.insertAction(first, act)
        if first is not None:
            menu.insertSeparator(first)

    def _passage_span(self, idx: int) -> tuple[int, int, int]:
        """A passage's span without the whitespace around it, and its segment index."""
        a, b, k = self._passages[idx]
        text = self.editor.toPlainText()
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        return a, b, k

    def said_by(self, n: int, sel: tuple[int, int] | None, pos: int):
        """`n` said the selection (or the paragraph at `pos`): whole passages are relabeled, words in
        part of a passage are split off into a paragraph of their own."""
        rec = self.rec
        if rec is None:
            return
        self._align_now()  # the text may have changed since the last alignment (it waits for a pause)
        if not self._passages:
            return
        if sel is None:
            idx = self._passage_at(pos)
            if idx is None:
                return
            sel = self._passage_span(idx)[:2]
        text = self.editor.toPlainText()
        cuts = []
        for idx in range(len(self._passages)):
            pa, pb, k = self._passage_span(idx)
            lo, hi = max(pa, sel[0]), min(pb, sel[1])
            while lo < hi and text[lo].isspace():
                lo += 1
            while hi > lo and text[hi - 1].isspace():
                hi -= 1
            if lo >= hi:
                continue
            if lo <= pa and hi >= pb:
                rec.fix_speaker(k, n)
            else:
                seg = self._segments[k]
                t0, t1 = float(seg.get("start", 0.0)), float(seg.get("end", 0.0))
                at = lambda x: round(t0 + (t1 - t0) * (x - pa) / max(1, pb - pa), 2)  # noqa: E731
                rec.fix_speaker(k, n, text[lo:hi], at(lo), at(hi))
                cuts.append((lo, hi))
        if cuts:
            self._break_around(cuts)  # a text edit: the passages' text moves, the fixes find their words
        self._relabel(rec, n)
        self._align_now()
        self._update_status(rec)
        self.changed.emit(rec.id)

    def _relabel(self, rec: Recording, n: int | None = None):
        """The rest of the recording reassigned from the user's fixes (relabel.py): a passage that
        sounds like a fixed one follows it. A transcript from before voiceprints were kept stays."""
        moved = relabel.relabel(rec)
        if moved is None:
            return
        self._reload_speakers(rec)
        if moved:
            who = rec.meta.speakers.get(str(rec.speaker(n))) if n is not None else None
            self.message.emit(f"{moved} more passage{'s' if moved != 1 else ''} moved to match"
                              + (f" what {who} said" if who else " your fix")
                              + ". “Back to the speakers Echo found” on a name undoes it.")

    def _reload_speakers(self, rec: Recording):
        self._segments = shown_segments(rec)
        self._shown_signature = self._signature(rec)  # the same text: no reload of the editor
        for k, name in rec.meta.speakers.items():  # their voice in this recording, as it now is
            if rec.speaker(int(k)) == int(k):
                self._remember_voice(rec, int(k), name)

    def restore_speakers(self):
        rec = self.rec
        if rec is None or not relabel.restore(rec):
            return
        self._reload_speakers(rec)
        self._align_now()
        self._update_status(rec)
        self.changed.emit(rec.id)

    def _break_around(self, cuts: list[tuple[int, int]]):
        """Paragraph breaks before and after each cut, as one undoable edit."""
        text = self.editor.toPlainText()
        cur = self.editor.textCursor()
        cur.beginEditBlock()
        for lo, hi in sorted(cuts, reverse=True):
            for at, after in ((hi, True), (lo, False)):
                a = b = at
                while a > 0 and text[a - 1] in " \t":
                    a -= 1
                while b < len(text) and text[b] in " \t":
                    b += 1
                if a == 0 or b == len(text) or "\n" in (text[a - 1], text[b]):
                    continue  # already at a paragraph's edge
                cur.setPosition(a)
                cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                cur.insertText("\n\n")
        cur.endEditBlock()

    def _said_by_someone_else(self, sel, pos: int):
        from PySide6.QtWidgets import QInputDialog

        rec = self.rec
        if rec is None:
            return
        n = max(rec.speaker_numbers() + [0]) + 1
        people = [e.name for e in dictionary.current().entries if e.kind == dictionary.PEOPLE]
        name, ok = QInputDialog.getItem(self, "Said by someone else", "Who said it?", people, -1, True)
        if not ok:
            return
        self.said_by(n, sel, pos)
        if name.strip():
            self.name_speaker(n, name.strip())

    def _fix_at(self, pos: int) -> tuple[int, str | None] | None:
        """(segment, words or None) of the user's fix at `pos`, if there is one."""
        rec, piece = self.rec, self._piece_at(pos)
        if rec is None or piece is None:
            return None
        s, e, k, _who = piece
        text = self.editor.toPlainText()
        fixes = [f for f in rec.fixes() if f.get("segment") == k]
        words = next((f["text"] for f in fixes if f.get("text") == text[s:e]), None)
        if words:
            return k, words
        return (k, None) if any(not f.get("text") for f in fixes) else None

    def unfix_at(self, pos: int):
        self._align_now()
        fix = self._fix_at(pos)
        if fix is None or self.rec is None:
            return
        self.rec.unfix_speaker(*fix)
        self._relabel(self.rec)
        self._align_now()
        self._update_status(self.rec)
        self.changed.emit(self.rec.id)

    def _break_before(self, pos: int) -> tuple[int, int] | None:
        """The blank line(s) before the paragraph at `pos`, as a span, if there is text above it."""
        text = self.editor.toPlainText()
        start = self.editor.document().findBlock(pos).position()
        a = start
        while a > 0 and text[a - 1].isspace():
            a -= 1
        return (a, start) if 0 < a < start and "\n" in text[a:start] else None

    def join_above(self, pos: int):
        span = self._break_before(pos)
        if span is None:
            return
        language = ((self.rec.transcript() if self.rec else None) or {}).get("language", "es")
        cur = self.editor.textCursor()
        cur.setPosition(span[0])
        cur.setPosition(span[1], QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(" " if align.separator(language) else "")
