"""Recording folders: the source of truth for everything the user creates.

Layout of one recording folder::

    <data>/recordings/<id>/
        meta.json                 metadata (atomic writes)
        takes/                    raw PCM takes, only while recording or awaiting finalize
        audio.<ext>               the original audio (recorded FLAC or imported file, unmodified)
        transcript.json           raw model output, segments with times (immutable per run)
        transcript.corrected.json the model output with dictionary corrections, each logged
        transcript.edited.txt     user edits, never overwritten by the transcriber
        transcribe.requested      job marker: transcription wanted (JSON options)
        transcribe.progress.json  written by the worker while running
        transcribe.error          last failure message
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .fsutil import atomic_write_json, atomic_write_text, read_json

META = "meta.json"
TAKES = "takes"
TRANSCRIPT = "transcript.json"
CORRECTED = "transcript.corrected.json"
EDITED = "transcript.edited.txt"
REQUESTED = "transcribe.requested"
PROGRESS = "transcribe.progress.json"
ERROR = "transcribe.error"

# Recording states
RECORDING = "recording"
NEEDS_FINALIZE = "needs_finalize"
READY = "ready"
FAILED = "failed"

# Transcript states (derived from files)
T_NONE = "none"
T_QUEUED = "queued"
T_RUNNING = "running"
T_DONE = "done"
T_FAILED = "failed"


def clean_tag(tag: str) -> str:
    """A tag as stored: 1 to 32 characters, no '#', commas or line breaks; '' if nothing is left."""
    t = " ".join(str(tag).replace("#", " ").replace(",", " ").split())
    return t[:32].strip()


def fold_tag(tag: str) -> str:
    """Tags compare without case or accents, like the search does."""
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", tag) if not unicodedata.combining(c)).casefold()


def tag_category(tag: str) -> tuple[str, str] | None:
    """`client:Acme` -> ("client", "Acme"): a tag's category and value; None for a plain tag."""
    cat, sep, value = tag.partition(":")
    cat, value = cat.strip(), value.strip()
    return (cat, value) if sep and cat and value else None


def auto_title(text: str, limit: int = 60) -> str:
    """The first sentence of a transcript as a title: cut at the sentence end or at a word
    boundary within `limit` characters, without trailing punctuation; "" if there is no text."""
    import re

    text = " ".join(text.split())
    m = re.search(r"[.!?…](\s|$)", text)
    first = text[:m.start()] if m else text
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0] if " " in first[:limit] else first[:limit]
    return first.strip(" ,;:-—¡¿!?.…\"'«»").strip()


def new_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"{now:%Y-%m-%dT%H-%M-%S}_{secrets.token_hex(2)}"


@dataclass
class Meta:
    id: str
    title: str
    created: str  # ISO 8601 local time with offset
    origin: str  # "recorded" | "imported"
    state: str = READY
    source: str = ""  # device description or original file name
    audio: str | None = None  # file name inside the folder
    sha256: str | None = None
    duration: float | None = None  # seconds
    sample_rate: int | None = None
    channels: int | None = None
    crop_start: float | None = None  # seconds; None = beginning
    crop_end: float | None = None  # seconds; None = end
    recovered: bool = False  # finalized after a crash
    gaps: list[dict[str, Any]] = field(default_factory=list)  # capture interruptions
    error: str | None = None
    context_line: str = ""  # "who is speaking, what about": context for this recording's transcription
    markers: list[dict[str, Any]] = field(default_factory=list)  # [{"at": seconds of audio, "note": str}]
    language: str | None = None  # transcription language code; None = the default in settings
    tags: list[str] = field(default_factory=list)  # as typed; compared folded (case and accents)
    notes: str = ""
    title_auto: bool = False  # a generated title, replaced by the transcript's first sentence
    quick_note: bool = False  # copy the transcript to the clipboard when it is ready (once)
    speakers: dict[str, str] = field(default_factory=dict)  # speaker number -> the name the user gave
    speakers_off: bool = False  # no speaker labels for this recording (a monologue)
    naming_dismissed: bool = False  # "Not now" on the naming bar: do not ask about its speakers again
    speaker_merges: dict[str, int] = field(default_factory=dict)  # speaker -> the speaker it is the same person as
    # "Said by": [{transcript, segment, speaker, name} + {text, start, end} for words split off a passage]
    speaker_fixes: list[dict[str, Any]] = field(default_factory=list)
    extracted_from: dict[str, Any] | None = None  # source video: name, sha256, size, track, method
    tracks: list[str] | None = None  # what each channel is, for a call: ["mic", "computer"]; None = one source

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Meta":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


class Recording:
    def __init__(self, folder: Path, meta: Meta):
        self.folder = Path(folder)
        self.meta = meta

    # ---- identity / files -------------------------------------------------
    @property
    def id(self) -> str:
        return self.meta.id

    @property
    def audio_path(self) -> Path | None:
        return self.folder / self.meta.audio if self.meta.audio else None

    @property
    def takes_dir(self) -> Path:
        return self.folder / TAKES

    def path(self, name: str) -> Path:
        return self.folder / name

    # ---- persistence -------------------------------------------------------
    def save(self) -> None:
        atomic_write_json(self.folder / META, asdict(self.meta))

    def reload(self) -> "Recording":
        self.meta = Meta.from_dict(read_json(self.folder / META))
        return self

    def update(self, **changes: Any) -> None:
        """Change some fields and save. The file is read first, so changes made by another process
        meanwhile (the window renaming a recording the supervisor is about to finalize) are kept."""
        try:
            self.reload()
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            pass  # not written yet: the fields in memory are all there is
        for k, v in changes.items():
            if not hasattr(self.meta, k):
                raise AttributeError(k)
            setattr(self.meta, k, v)
        self.save()

    # ---- transcript ---------------------------------------------------------
    # ---- speakers ------------------------------------------------------------
    def speaker(self, number: int | None) -> int | None:
        """A passage's speaker after the user's merges: the speaker it is the same person as."""
        seen: set[int] = set()
        while number is not None and str(number) in self.meta.speaker_merges and number not in seen:
            seen.add(number)
            number = int(self.meta.speaker_merges[str(number)])
        return number

    def merged_into(self, number: int) -> list[int]:
        """The speakers merged into `number`, itself not included."""
        return sorted(int(k) for k in self.meta.speaker_merges if self.speaker(int(k)) == number and int(k) != number)

    def fixes(self, transcript: dict | None = None) -> list[dict[str, Any]]:
        """The user's "Said by" fixes for the current transcript (older ones are kept, not applied)."""
        created = (transcript if transcript is not None else self.transcript() or {}).get("created")
        return [f for f in self.meta.speaker_fixes if f.get("transcript") == created]

    def speaker_at(self, k: int, segment: dict, fixes: list[dict] | None = None) -> int | None:
        """Passage k's speaker: the user's fix for the whole passage, else the model's; after merges."""
        n = segment.get("speaker")
        for f in self.fixes() if fixes is None else fixes:
            if f.get("segment") == k and not f.get("text"):
                n = f["speaker"]
        return self.speaker(n)

    def fix_speaker(self, segment: int, speaker: int, text: str | None = None,
                    start: float | None = None, end: float | None = None) -> None:
        """Record that passage `segment` (or the words `text` in it) was said by `speaker`. A
        whole-passage fix replaces an earlier one for that passage; words replace a fix of the
        same words. Name and times are kept with it, as data for tuning the labeling later."""
        t = self.transcript() or {}
        created = t.get("created")
        fix: dict[str, Any] = {"transcript": created, "segment": segment, "speaker": int(speaker),
                               "name": self.meta.speakers.get(str(self.speaker(int(speaker)))) or ""}
        if text:
            fix.update(text=text, start=start, end=end)
        keep = [f for f in self.meta.speaker_fixes
                if not (f.get("transcript") == created and f.get("segment") == segment
                        and (f.get("text") or None) == (text or None))]
        self.update(speaker_fixes=keep + [fix])

    def unfix_speaker(self, segment: int, text: str | None = None) -> bool:
        """Drop the current transcript's fix of passage `segment` (or of the words `text` in it)."""
        created = (self.transcript() or {}).get("created")
        keep = [f for f in self.meta.speaker_fixes
                if not (f.get("transcript") == created and f.get("segment") == segment
                        and (f.get("text") or None) == (text or None))]
        if len(keep) == len(self.meta.speaker_fixes):
            return False
        self.update(speaker_fixes=keep)
        return True

    def speaker_numbers(self) -> list[int]:
        """Every speaker of the recording after merges: the model's and any the user added."""
        t = self.transcript() or {}
        count = int((t.get("speakers") or {}).get("count", 0))
        nums = {self.speaker(i) for i in range(1, count + 1)}
        nums |= {self.speaker(int(f["speaker"])) for f in self.fixes(t)}
        return sorted(n for n in nums if n is not None)

    def merge_speakers(self, source: int, target: int) -> None:
        """`source` is the same person as `target`: it takes target's number and name, or gives target
        its name when target had none. The model's transcript is not touched."""
        source, target = self.speaker(source), self.speaker(target)
        if source is None or target is None or source == target:
            return
        merges = {k: (target if v == source else v) for k, v in self.meta.speaker_merges.items()}
        merges[str(source)] = target
        names = dict(self.meta.speakers)
        moved = names.pop(str(source), None)
        if moved and str(target) not in names:
            names[str(target)] = moved
        self.update(speaker_merges=merges, speakers=names)

    def separate_speakers(self, target: int) -> list[int]:
        """Undo every merge into `target`; the separated speakers are unnamed. Returns them."""
        parts = self.merged_into(target)
        self.update(speaker_merges={k: v for k, v in self.meta.speaker_merges.items() if int(k) not in parts})
        return parts

    def transcript_status(self) -> str:
        if self.path(REQUESTED).exists():
            return T_RUNNING if self.path(PROGRESS).exists() else T_QUEUED
        if self.path(TRANSCRIPT).exists():
            return T_DONE
        if self.path(ERROR).exists():
            return T_FAILED
        return T_NONE

    def transcript(self) -> dict[str, Any] | None:
        try:
            return read_json(self.path(TRANSCRIPT))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def model_text(self) -> str:
        t = self.transcript()
        return t.get("text", "") if t else ""

    def corrected(self) -> dict[str, Any] | None:
        """The dictionary-corrected copy of the current model transcript, if there is one."""
        from .dictionary import read_corrected

        return read_corrected(self)

    def base_text(self) -> str:
        """The text before the user's edits: the corrected model output, else the model output."""
        c = self.corrected()
        return c.get("text", "") if c else self.model_text()

    def text(self) -> str:
        """What the user sees: their edited text if any, else the (corrected) model output."""
        edited = self.path(EDITED)
        if edited.exists():
            return edited.read_text(encoding="utf-8")
        return self.base_text()

    def is_edited(self) -> bool:
        return self.path(EDITED).exists()

    def save_edited(self, text: str) -> None:
        atomic_write_text(self.path(EDITED), text)

    def revert_edits(self) -> None:
        try:
            self.path(EDITED).unlink()
        except FileNotFoundError:
            pass

    def progress(self) -> dict[str, Any] | None:
        try:
            return read_json(self.path(PROGRESS))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def request_transcription(self, **options: Any) -> None:
        for name in (ERROR, PROGRESS):
            try:
                self.path(name).unlink()
            except FileNotFoundError:
                pass
        atomic_write_json(self.path(REQUESTED), {"requested": time.time(), **options})

    def cancel_transcription(self) -> None:
        for name in (REQUESTED, PROGRESS):
            try:
                self.path(name).unlink()
            except FileNotFoundError:
                pass

    def error_text(self) -> str | None:
        try:
            return self.path(ERROR).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None

    def effective_span(self) -> tuple[float, float | None]:
        return (self.meta.crop_start or 0.0, self.meta.crop_end)

    def set_tags(self, tags) -> list[str]:
        """Save valid tags, one per folded spelling, in the order given. Returns them."""
        out: list[str] = []
        for t in tags:
            t = clean_tag(t)
            if t and fold_tag(t) not in {fold_tag(x) for x in out}:
                out.append(t)
        self.update(tags=out)
        return out

    def set_markers(self, markers: list[dict[str, Any]]) -> None:
        """Save markers sorted by time, each {"at": seconds, "note": text}."""
        clean = [{"at": round(max(0.0, float(m["at"])), 2), "note": str(m.get("note") or "").strip()}
                 for m in markers]
        self.update(markers=sorted(clean, key=lambda m: m["at"]))


class Library:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.recordings_dir = self.data_dir / "recordings"
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

    def create(self, title: str, origin: str, **meta: Any) -> Recording:
        now = datetime.now().astimezone()
        rid = new_id(now)
        folder = self.recordings_dir / rid
        folder.mkdir()
        rec = Recording(folder, Meta(id=rid, title=title, created=now.isoformat(timespec="seconds"),
                                     origin=origin, **meta))
        rec.save()
        return rec

    def get(self, rid: str) -> Recording | None:
        folder = self.recordings_dir / rid
        try:
            return Recording(folder, Meta.from_dict(read_json(folder / META)))
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return None

    def all(self) -> list[Recording]:
        out = []
        for folder in sorted(self.recordings_dir.iterdir(), reverse=True):
            if folder.is_dir() and not folder.name.startswith("."):
                rec = self.get(folder.name)
                if rec is None and (folder / TAKES).is_dir():
                    rec = self._salvage(folder)
                if rec:
                    out.append(rec)
        return out

    def _salvage(self, folder: Path) -> Recording:
        """A folder with takes but no readable meta (crash during creation): rebuild meta."""
        rec = Recording(folder, Meta(id=folder.name, title=f"Recovered {folder.name[:16]}",
                                     created=datetime.now().astimezone().isoformat(timespec="seconds"),
                                     origin="recorded", state=NEEDS_FINALIZE, recovered=True))
        rec.save()
        return rec

    def delete(self, rec: Recording) -> Path | None:
        """Move the folder to the desktop trash, or to <data>/trash where there is none.
        Returns the new location when it is known."""
        if os.name != "nt" and sys.platform != "darwin":
            # Linux: the freedesktop trash, written here so the folders are resolved at call time.
            return move_to_trash(rec.folder, self.data_dir / "trash")
        try:
            from send2trash import send2trash

            send2trash(str(rec.folder))
            return None
        except Exception:  # noqa: BLE001 - no usable trash (network drive): keep it ourselves
            dest_dir = self.data_dir / "trash"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / rec.folder.name
            shutil.move(str(rec.folder), dest)
            return dest


def move_to_trash(path: Path, fallback_dir: Path) -> Path:
    """freedesktop.org trash spec, home trash only; fall back to a local folder across devices."""
    path = Path(path)
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    trash = data_home / "Trash"
    try:
        same_fs = os.stat(path).st_dev == os.stat(data_home if data_home.exists() else Path.home()).st_dev
    except OSError:
        same_fs = False
    if same_fs:
        files, info = trash / "files", trash / "info"
        files.mkdir(parents=True, exist_ok=True)
        info.mkdir(parents=True, exist_ok=True)
        name = path.name
        n = 1
        while (files / name).exists() or (info / f"{name}.trashinfo").exists():
            n += 1
            name = f"{path.name}.{n}"
        info_text = ("[Trash Info]\n"
                     f"Path={urllib.parse.quote(str(path.resolve()))}\n"
                     f"DeletionDate={datetime.now():%Y-%m-%dT%H:%M:%S}\n")
        # Write the info file first (spec requirement), exclusive create.
        with open(info / f"{name}.trashinfo", "x", encoding="utf-8") as f:
            f.write(info_text)
        dest = files / name
        os.rename(path, dest)
        return dest
    fallback_dir.mkdir(parents=True, exist_ok=True)
    dest = fallback_dir / path.name
    shutil.move(str(path), dest)
    return dest
