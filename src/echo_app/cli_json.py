"""One recording as a JSON-ready dict, the same in every command's --json output (stdlib only).

Scripts and agents read these keys, so keys are only ever added, never renamed or removed.
"""

from __future__ import annotations

from typing import Any

from .library import CORRECTED, EDITED, TRANSCRIPT, Recording

KEYS = ("id", "title", "created", "duration", "source", "extracted_from", "state", "transcript_status",
        "progress", "error", "language", "speakers", "tags", "notes", "folder", "audio", "files")


def _file(rec: Recording, name: str) -> str | None:
    p = rec.path(name)
    return str(p.resolve()) if p.exists() else None


def progress_of(rec: Recording) -> dict[str, Any] | None:
    """{"stage", "fraction", "eta_s"} while the worker runs on it, else None."""
    p = rec.progress()
    if not p:
        return None
    total = p.get("total") or 0
    frac = min(1.0, (p.get("done") or 0) / total) if total else 0.0
    eta = p.get("eta_s")
    return {"stage": p.get("stage"), "fraction": round(frac, 3), "eta_s": round(eta) if eta is not None else None}


def speakers_of(rec: Recording) -> dict[str, Any] | None:
    from . import export

    if not export.has_speakers(rec):
        return None
    names = export._names(rec) or {}
    return {"count": len(names), "names": [names[n] for n in sorted(names)]}


def record(rec: Recording) -> dict[str, Any]:
    from . import transcription

    status = rec.transcript_status()
    audio = rec.audio_path
    return {
        "id": rec.id,
        "title": rec.meta.title,
        "created": rec.meta.created,
        "duration": rec.meta.duration,
        "source": rec.meta.source,
        "extracted_from": rec.meta.extracted_from,
        "state": rec.meta.state,
        "transcript_status": status,
        "progress": progress_of(rec) if status == "running" else None,
        "error": rec.error_text() if status == "failed" else None,
        "language": transcription.language_of(rec),
        "speakers": speakers_of(rec),
        "tags": list(rec.meta.tags),
        "notes": rec.meta.notes,
        "folder": str(rec.folder.resolve()),
        "audio": str(audio.resolve()) if audio and audio.exists() else None,
        "files": {"transcript": _file(rec, TRANSCRIPT), "corrected": _file(rec, CORRECTED),
                  "edited": _file(rec, EDITED)},
    }
