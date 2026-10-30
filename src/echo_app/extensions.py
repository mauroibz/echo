"""Optional packages that add to Echo (stdlib only). None ship with Echo; without one, nothing changes.

An extension is a package named in KNOWN, importable next to `echo_app`. Its top-level module may
define any of these hooks, each called only where Echo already does that kind of work:

    register_cli(subparsers)            add subcommands
    doctor_checks() -> [doctor.Check]   more lines in `echo-app doctor` and Check setup
    markdown_sections(rec) -> [(heading, markdown)]   sections in a recording's exported note
    settings_pages() -> [(title, QWidget)]   Settings tabs; a page's apply() runs on OK
    window_class() -> type[MainWindow]  open this window instead (the first one returned wins)
    attach_window(window)               called once the window is built; it may call
                                        window.add_view, add_screen and show_recording
    person_sections(name) -> [(title, QWidget)]   sections under a person's notes in People

The core never imports an extension directly (tests/test_extensions.py checks), and an extension
that raises is logged and skipped, so recording and transcription never depend on its code.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from functools import cache
from types import ModuleType

log = logging.getLogger(__name__)

KNOWN = ("echo_studio",)


def chosen() -> tuple[str, ...]:
    """The extensions to load: those the installer included (`install.sh --with-studio`), which the
    launcher passes as ECHO_EXTENSIONS; every known one present when Echo runs without the launcher
    (from a checkout, in tests)."""
    if os.environ.get("ECHO_NO_EXTENSIONS"):
        return ()
    if "ECHO_EXTENSIONS" in os.environ:
        wanted = {n.strip() for n in os.environ["ECHO_EXTENSIONS"].replace(",", " ").split()}
        return tuple(n for n in KNOWN if n in wanted)
    return KNOWN


@cache
def loaded() -> tuple[ModuleType, ...]:
    mods = []
    for name in chosen():
        try:
            if importlib.util.find_spec(name) is None:
                continue
            mods.append(importlib.import_module(name))
        except Exception:
            log.exception("extension %s could not be loaded; Echo runs without it", name)
    return tuple(mods)


def call(hook: str, *args) -> list:
    """Each loaded extension's result for `hook`, skipping extensions without it or that raise."""
    results = []
    for mod in loaded():
        fn = getattr(mod, hook, None)
        if fn is None:
            continue
        try:
            results.append(fn(*args))
        except Exception:
            log.exception("extension %s failed in %s", mod.__name__, hook)
    return results


def gather(hook: str, *args) -> list:
    """`call` for hooks that return lists, joined into one."""
    out = []
    for r in call(hook, *args):
        out.extend(r or ())
    return out
