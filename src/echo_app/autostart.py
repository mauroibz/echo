"""Starting Echo at login, in the tray: an XDG autostart entry (stdlib only).

The entry runs the same launcher as the menu entry with `gui --background`, so Echo starts
without its window and keeps running when the window is closed. It exists only while the
"Keep Echo running in the tray" setting is on; Settings writes or removes it.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

NAME = "echo-app.desktop"


def path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / NAME


def launcher() -> str:
    """The installed launcher (~/.local/bin/echo-app), else the one in this source tree."""
    found = shutil.which("echo-app")
    if found:
        return found
    tree = Path(__file__).resolve().parents[2] / "bin" / "echo-app"
    return str(tree) if tree.exists() else f"{sys.executable} -m echo_app"


def entry() -> str:
    return ("[Desktop Entry]\nType=Application\nName=Echo\nComment=Keeps Echo running in the tray\n"
            f"Exec={launcher()} gui --background\nIcon=echo-app\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")


def enabled() -> bool:
    return path().exists()


def set_enabled(on: bool) -> None:
    from .fsutil import atomic_write_text

    p = path()
    if on:
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(p, entry())
    else:
        p.unlink(missing_ok=True)
