"""The user's marks on a meeting, in marks.json in the recording's folder (stdlib only).

For now one: a star, for the meetings worth finding again. It is the user's, so summarizing again
never touches it; tags stay Echo's own (the recording's tags), so they work in search as well.
"""

from __future__ import annotations

from echo_app.fsutil import atomic_write_json, read_json
from echo_app.library import Recording

FILE = "marks.json"


def load(rec: Recording) -> dict:
    try:
        d = read_json(rec.path(FILE))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def starred(rec: Recording) -> bool:
    return bool(load(rec).get("starred"))


def set_starred(rec: Recording, on: bool) -> None:
    d = load(rec)
    d["starred"] = bool(on)
    atomic_write_json(rec.path(FILE), d)
