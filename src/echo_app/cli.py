"""`echo-app` command line. With no arguments it opens the window."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__


def _cmd_rescan(args) -> int:
    from .index import Index
    from .library import Library
    from .settings import load

    from . import sets

    cfg, _ = load()
    lib = Library(cfg.data_path)
    gone = sets.cleanup(lib)
    idx = Index(lib)
    n = idx.rebuild()
    print(f"Indexed {n} recording(s) in {cfg.data_path}")
    if gone:
        print(f"Removed {gone} empty linked set file(s)")
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
    lib = Library(cfg.data_path)
    idx = Index(lib)
    idx.sync()
    rows = idx.list(args.query or "", tags=args.tag or ())
    if args.json:
        import json

        from . import cli_json

        recs = [rec for rec in (lib.get(r["id"]) for r in rows) if rec is not None]
        ids = {rec.id for rec in recs}
        sets = [{"id": st["id"], "title": st["title"], "members": list(st["members"])}
                for st in idx.sets() if ids & set(st["members"])]
        print(json.dumps({"recordings": [cli_json.record(rec) for rec in recs], "sets": sets},
                         ensure_ascii=False, indent=2))
        return 0
    by_id = {r["id"]: r for r in rows}
    linked = {m: st for st in idx.sets() for m in st["members"]}

    def line(r, indent=""):
        rec = lib.get(r["id"])
        n = len(rec.meta.markers) if rec else 0
        marks = f"  [{n} marker{'s' if n != 1 else ''}]" if n else ""
        tags = "  " + " ".join(f"#{t}" for t in rec.meta.tags) if rec and rec.meta.tags else ""
        print(f"{indent}{r['id']}  {_fmt_dur(r['duration']):>8}  {r['transcript_status']:<8}  {r['title']}{marks}{tags}")

    shown = set()
    for r in rows:
        st = linked.get(r["id"])
        if st is None:
            line(r)
        elif st["id"] not in shown:
            # A set prints once, where its first matching part would be, with its matching parts.
            shown.add(st["id"])
            total = sum(by_id[m]["duration"] or 0 for m in st["members"] if m in by_id)
            print(f"{st['id']}  {_fmt_dur(total):>8}  {len(st['members'])} parts  {st['title']}")
            for m in st["members"]:
                if m in by_id:
                    line(by_id[m], "  ")
    if not rows:
        print("No recordings." if not (args.query or args.tag) else "No matches.")
    return 0


def _cmd_tag(args) -> int:
    from .library import Library, fold_tag
    from .settings import load

    cfg, _ = load()
    rec = Library(cfg.data_path).get(args.id)
    if rec is None:
        print(f"No recording {args.id}", file=sys.stderr)
        return 1
    tags = list(rec.meta.tags)
    for change in args.changes:
        if change.startswith("-") and len(change) > 1:
            tags = [t for t in tags if fold_tag(t) != fold_tag(change[1:])]
        elif change.strip("+"):
            tags.append(change.lstrip("+"))
    tags = rec.set_tags(tags)
    print(" ".join(f"#{t}" for t in tags) or "No tags.")
    return 0


def _cmd_export(args) -> int:
    from . import export
    from .library import READY, Library
    from .settings import load

    cfg, _ = load()
    if args.all:
        lib = Library(cfg.data_path)
        recs = [r for r in lib.all() if r.meta.state == READY]
        counts = export.export_folder(recs, Path(args.all).expanduser(), timestamps=args.timestamps,
                                      audio=args.audio)
        print(f"{counts['written']} written, {counts['unchanged']} up to date in {args.all}")
        return 0
    if not args.id:
        print("Give a recording id, or --all FOLDER.", file=sys.stderr)
        return 2
    from . import sets

    lib = Library(cfg.data_path)
    fmt = "." + args.format if args.format else (Path(args.out).suffix.lower() if args.out else ".txt")
    if fmt not in export.TEXT_FORMATS:
        print(f"Unknown format {fmt}; use one of: {', '.join(f[1:] for f in export.TEXT_FORMATS)}", file=sys.stderr)
        return 2
    if sets.is_set_id(args.id):
        st = sets.get(lib, args.id)
        if st is None:
            print(f"No linked set {args.id}", file=sys.stderr)
            return 1
        parts = sets.present(lib, st)
        if not any(r.text().strip() for r in parts):
            print("No part of that set has a transcript yet.", file=sys.stderr)
            return 1
        text = export.render_set(st.title, parts, fmt, st.id)
    else:
        rec = lib.get(args.id)
        if rec is None:
            print(f"No recording {args.id}", file=sys.stderr)
            return 1
        if not rec.text().strip():
            print("That recording has no transcript yet.", file=sys.stderr)
            return 1
        text = export.render_transcript(rec, fmt)
    if not args.out:
        sys.stdout.write(text)
        return 0
    out = Path(args.out)
    if out.suffix.lower() != fmt:
        out = out.with_suffix(fmt)
    out.write_text(text, encoding="utf-8")
    print(f"Saved {out}")
    return 0


def _cmd_link(args) -> int:
    from . import sets
    from .library import Library
    from .settings import load

    cfg, _ = load()
    try:
        st = sets.link(Library(cfg.data_path), args.ids, title=args.title)
    except KeyError as e:
        print(f"No recording or set {e.args[0]}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(f"{st.id}  {len(st.members)} parts  {st.title}")
    return 0


def _cmd_unlink(args) -> int:
    from . import sets
    from .library import Library
    from .settings import load

    cfg, _ = load()
    lib = Library(cfg.data_path)
    if sets.is_set_id(args.id):
        if sets.get(lib, args.id) is None:
            print(f"No linked set {args.id}", file=sys.stderr)
            return 1
        sets.dissolve(lib, args.id)
        print("Unlinked.")
    elif sets.set_of(lib, args.id) is None:
        print(f"{args.id} is not in a linked set", file=sys.stderr)
        return 1
    else:
        sets.unlink(lib, args.id)
        print("Removed from its set.")
    return 0


def _cmd_doctor(args) -> int:
    from . import doctor

    return doctor.main(args)


def _cmd_gui(args) -> int:
    from .ui.app import run

    return run(sys.argv[:1] + list(getattr(args, "files", []) or []))


COMMANDS: dict[str, tuple[str, object]] = {}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="echo-app", description="Record and transcribe audio locally.")
    p.add_argument("--version", action="version", version=f"Echo {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="log to stderr")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    s = sub.add_parser("gui", help="open the window (default); files given are imported")
    s.add_argument("files", nargs="*")
    s.set_defaults(func=_cmd_gui)

    s = sub.add_parser("list", help="list recordings")
    s.add_argument("query", nargs="?", help="search titles, notes and transcripts; #word is a tag")
    s.add_argument("--tag", action="append", metavar="TAG", help="only recordings with this tag (repeatable)")
    s.add_argument("--json", action="store_true", help="print recordings and linked sets as JSON")
    s.set_defaults(func=_cmd_list)

    s = sub.add_parser("rescan", help="rebuild the library index from the recording folders")
    s.set_defaults(func=_cmd_rescan)

    s = sub.add_parser("tag", help="show, add (+tag) or remove (-tag) a recording's tags")
    s.add_argument("id")
    s.add_argument("changes", nargs=argparse.REMAINDER, metavar="+TAG|-TAG")
    s.set_defaults(func=_cmd_tag)

    s = sub.add_parser("export", help="write a transcript or linked set as text, Markdown, subtitles or JSON, "
                                      "or every recording as Markdown notes into a folder")
    s.add_argument("id", nargs="?")
    s.add_argument("--all", metavar="FOLDER", help="one Markdown note per recording into FOLDER (a vault)")
    s.add_argument("--audio", choices=["link", "copy", "none"], default="link",
                   help="with --all: link to Echo's audio file, copy it next to the notes, or neither")
    s.add_argument("--timestamps", action="store_true", help="with --all: start paragraphs with their time")
    s.add_argument("--format", choices=["txt", "md", "srt", "vtt", "json"],
                   help="default: from the --out suffix, else txt")
    s.add_argument("--out", metavar="PATH", help="file to write; default: standard output")
    s.set_defaults(func=_cmd_export)

    s = sub.add_parser("link", help="link recordings into one set, read and played in order "
                                    "(a set id among them: add to that set)")
    s.add_argument("ids", nargs="+", metavar="ID")
    s.add_argument("--title", help="the set's title (default: from its first part)")
    s.set_defaults(func=_cmd_link)

    s = sub.add_parser("unlink", help="dissolve a linked set, or take one recording out of its set")
    s.add_argument("id")
    s.set_defaults(func=_cmd_unlink)

    s = sub.add_parser("doctor", help="check prerequisites and install health")
    s.add_argument("--no-gpu", action="store_true", help="skip the GPU probe")
    s.set_defaults(func=_cmd_doctor)

    for register in _extensions():
        register(sub)
    return p


def _extensions():
    """Subcommands contributed by other modules (recorder, import, worker)."""
    from . import cli_ext, cli_rec, cli_tr  # noqa: F401 - registers subcommands

    return cli_ext.REGISTRARS


def main(argv: list[str] | None = None) -> int:
    from . import logs

    parser = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    # "echo-app file.opus" (desktop "Open with") means: open the window and import the file.
    if argv and not argv[0].startswith("-") and argv[0] not in _command_names(parser):
        argv = ["gui", *argv]
    args = parser.parse_args(argv)
    name = getattr(args, "command", None) or "gui"
    logs.setup({"gui": "gui", "_recorder": "recorder", "_worker": "worker"}.get(name, "cli"), verbose=args.verbose)
    if not args.command:
        return _cmd_gui(args)
    return args.func(args) or 0


def _command_names(parser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def gui_main() -> int:
    return main([])
