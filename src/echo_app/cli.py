"""`echo-app` command line. With no arguments it opens the window."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def _cmd_rescan(args) -> int:
    from .index import Index
    from .library import Library
    from .settings import load

    cfg, _ = load()
    idx = Index(Library(cfg.data_path))
    n = idx.rebuild()
    print(f"Indexed {n} recording(s) in {cfg.data_path}")
    return 0


def _fmt_dur(sec) -> str:
    if sec is None:
        return "--:--"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _cmd_list(args) -> int:
    from .index import Index
    from .library import Library
    from .settings import load

    cfg, _ = load()
    idx = Index(Library(cfg.data_path))
    idx.sync()
    rows = idx.list(args.query or "")
    for r in rows:
        print(f"{r['id']}  {_fmt_dur(r['duration']):>8}  {r['transcript_status']:<8}  {r['title']}")
    if not rows:
        print("No recordings." if not args.query else "No matches.")
    return 0


def _cmd_doctor(args) -> int:
    from . import doctor

    return doctor.main(args)


def _cmd_gui(args) -> int:
    from .ui.app import run

    return run(sys.argv[:1])


COMMANDS: dict[str, tuple[str, object]] = {}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="echo-app", description="Record and transcribe audio locally.")
    p.add_argument("--version", action="version", version=f"Echo {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="log to stderr")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    s = sub.add_parser("gui", help="open the window (default)")
    s.set_defaults(func=_cmd_gui)

    s = sub.add_parser("list", help="list recordings")
    s.add_argument("query", nargs="?", help="search titles and transcripts")
    s.set_defaults(func=_cmd_list)

    s = sub.add_parser("rescan", help="rebuild the library index from the recording folders")
    s.set_defaults(func=_cmd_rescan)

    s = sub.add_parser("doctor", help="check prerequisites and install health")
    s.add_argument("--no-gpu", action="store_true", help="skip the GPU probe")
    s.set_defaults(func=_cmd_doctor)

    for register in _extensions():
        register(sub)
    return p


def _extensions():
    """Subcommands contributed by other modules (recorder, import, worker)."""
    from . import cli_ext, cli_rec  # noqa: F401 - registers subcommands

    return cli_ext.REGISTRARS


def main(argv: list[str] | None = None) -> int:
    from . import logs

    parser = build_parser()
    args = parser.parse_args(argv)
    name = getattr(args, "command", None) or "gui"
    logs.setup({"_recorder": "recorder", "_worker": "worker"}.get(name, name), verbose=args.verbose)
    if not args.command:
        return _cmd_gui(args)
    return args.func(args) or 0


def gui_main() -> int:
    return main([])
