"""Recording commands: record, pause, resume, stop, status, sources, recover, finalize."""

from __future__ import annotations

import argparse
import signal
import sys
import time

from . import cli_ext


def _lib():
    from .library import Library
    from .settings import load

    cfg, _ = load()
    return cfg, Library(cfg.data_path)


def _active_or_fail(lib):
    from . import recorder

    s = recorder.active(lib)
    if s is None:
        print("Not recording.", file=sys.stderr)
    return s


def _fmt(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def cmd_sources(args) -> int:
    from .audio import backend

    try:
        sources = backend.get().list_sources()
    except backend.BackendMissing as e:
        print(e, file=sys.stderr)
        return 1
    if not sources:
        print("No audio inputs found. Run: echo-app doctor", file=sys.stderr)
        return 1
    for s in sources:
        mark = "*" if s.is_default and s.kind == backend.INPUT else " "
        print(f"{mark} {s.label}\n    {s.name}")
    return 0


def cmd_record(args) -> int:
    from . import recorder

    cfg, lib = _lib()
    recorder.recover_all(lib)
    if args.toggle or args.quick_note:
        active = recorder.active(lib)
        if active is not None:  # the same key stops what it started
            print(f"Stopping \"{active.rec.meta.title}\"")
            code = _finish(active)
            if code == 0 and args.wait and active.rec.meta.quick_note:
                return _print_quick_note(lib, active.rec.id)
            return code
    source = args.source if args.source is not None else cfg.source
    # The remembered choice applies only where it can; an explicit flag that cannot is an error.
    # A quick note is the user alone, whatever the setting says.
    computer_audio = args.computer_audio
    if computer_audio is None:
        computer_audio = cfg.computer_audio and not args.quick_note and recorder.can_add_computer_audio(source)
    try:
        sess = recorder.start(lib, source=source, rate=cfg.sample_rate, channels=cfg.channels, title=args.title,
                              quick_note=args.quick_note, computer_audio=computer_audio)
    except recorder.RecorderError as e:
        print(e, file=sys.stderr)
        return 1
    st = sess.status()
    print(f"Recording \"{sess.rec.meta.title}\" from {sess.rec.meta.source or 'default input'}")
    print(f"  id: {sess.rec.id}")
    if not args.wait or args.toggle or args.quick_note:
        print("Stop with: echo-app stop" + (" (or the same command again)" if args.toggle or args.quick_note else ""))
        return 0
    stopping = False

    def on_int(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, on_int)
    signal.signal(signal.SIGTERM, on_int)
    print("Press Ctrl+C to stop.")
    while not stopping:
        st = sess.status()
        warn = f"  ! {st['warning']}" if st.get("warning") else ""
        print(f"\r  {st.get('state', ''):<10} {_fmt(st.get('elapsed', 0))}{warn}   ", end="", flush=True)
        if not sess.alive():
            print("\nThe recorder stopped unexpectedly; run: echo-app recover", file=sys.stderr)
            return 1
        time.sleep(0.5)
    print("\nStopping and saving...")
    return _finish(sess)


def _finish(sess) -> int:
    outcome = sess.stop(wait=600)
    if outcome == "ready":
        m = sess.rec.reload().meta
        print(f"Saved {_fmt(m.duration or 0)} to {sess.rec.audio_path}")
        return 0
    if outcome == "empty":
        print("Nothing was captured; the empty recording was discarded.")
        return 0
    print(f"Saving failed: {sess.rec.reload().meta.error}. Raw audio is kept; retry with: "
          f"echo-app finalize {sess.rec.id}", file=sys.stderr)
    return 1


def _print_quick_note(lib, rid: str, timeout: float = 600) -> int:
    """Wait for a quick note's transcript and print it (pipe it to wl-copy or xclip)."""
    from .library import T_DONE, T_FAILED, T_NONE

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rec = lib.get(rid)
        if rec is None:
            print("The note had no audio.", file=sys.stderr)
            return 1
        st = rec.transcript_status()
        if st == T_DONE:
            print(rec.text().strip())
            rec.update(quick_note=False)
            return 0
        if st in (T_FAILED, T_NONE):
            print("The note was not transcribed" + (f": {rec.error_text()}" if st == T_FAILED else
                                                    " (transcription is off or not installed)."), file=sys.stderr)
            return 1
        time.sleep(0.5)
    print("Timed out waiting for the transcript.", file=sys.stderr)
    return 1


def cmd_stop(args) -> int:
    _, lib = _lib()
    s = _active_or_fail(lib)
    return _finish(s) if s else 1


def cmd_pause(args) -> int:
    _, lib = _lib()
    s = _active_or_fail(lib)
    if not s:
        return 1
    s.pause()
    print("Paused.")
    return 0


def cmd_resume(args) -> int:
    _, lib = _lib()
    s = _active_or_fail(lib)
    if not s:
        return 1
    s.resume()
    print("Resumed.")
    return 0


def cmd_mark(args) -> int:
    from . import recorder

    _, lib = _lib()
    s = _active_or_fail(lib)
    if not s:
        return 1
    try:
        s.mark(args.note or "")
    except recorder.RecorderError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Marked at {_fmt(s.status().get('elapsed', 0))}" + (f": {args.note}" if args.note else ""))
    return 0


def cmd_markers(args) -> int:
    _, lib = _lib()
    rec = lib.get(args.id)
    if rec is None:
        print(f"No recording {args.id}", file=sys.stderr)
        return 1
    from . import recorder

    markers = rec.meta.markers or recorder.Session(rec).markers()
    for m in markers:
        print(f"{_fmt(m['at'])}  {m.get('note', '')}".rstrip())
    if not markers:
        print("No markers.")
    return 0


def cmd_status(args) -> int:
    _, lib = _lib()
    from . import recorder

    s = recorder.active(lib)
    if s is None:
        print("Not recording.")
        return 0
    st = s.status()
    print(f"{st.get('state')}  {_fmt(st.get('elapsed', 0))}  \"{s.rec.meta.title}\"  ({st.get('source')})")
    if st.get("warning"):
        print(f"  ! {st['warning']}")
    return 0


def cmd_recover(args) -> int:
    from . import recorder

    _, lib = _lib()
    actions = recorder.recover_all(lib)
    for rid, action in actions:
        print(f"{rid}: {action}")
    if not actions:
        print("Nothing to recover.")
    return 0


def cmd_finalize(args) -> int:
    from . import recorder

    _, lib = _lib()
    rec = lib.get(args.id)
    if rec is None:
        print(f"No recording {args.id}", file=sys.stderr)
        return 1
    if recorder.Session(rec).alive():
        print("That recording is still running; stop it first.", file=sys.stderr)
        return 1
    outcome = recorder.finalize(rec)
    print(outcome)
    return 0 if outcome != "failed" else 1


def cmd_import(args) -> int:
    from pathlib import Path

    from . import importer

    cfg, lib = _lib()
    importer.clean_staging(lib)
    if args.watch:
        from . import watch

        folders = [Path(p).expanduser() for p in args.paths] or [Path(p).expanduser() for p in cfg.watch_dirs]
        if not folders:
            print("No folders to watch. Give some, or add them in Settings → Import.", file=sys.stderr)
            return 1
        try:
            watch.watch_forever(lib, folders, interval=args.interval)
        except KeyboardInterrupt:
            pass
        return 0
    if not args.paths:
        print("Give files or folders to import (or --watch).", file=sys.stderr)
        return 2

    def progress(i, n, path, frac=None):
        if path.name and sys.stdout.isatty():
            pct = f" {frac:4.0%}" if frac is not None else "     "
            print(f"\r  [{i + 1}/{n}] {path.name[:55]:<55}{pct}", end="", flush=True)

    results = importer.import_paths(lib, [Path(p) for p in args.paths], progress=progress,
                                    auto_transcribe=None if not args.no_transcribe else False)
    if sys.stdout.isatty():
        print("\r" + " " * 72 + "\r", end="")
    if not results:
        print("No audio or video files found.", file=sys.stderr)
        return 1
    marks = {importer.IMPORTED: "+", importer.DUPLICATE: "=", importer.REJECTED: "!"}
    for r in results:
        print(f"{marks[r.status]} {r.source.name}: {r.message}")
    n = sum(r.status == importer.IMPORTED for r in results)
    print(f"{n} imported, {len(results) - n} skipped.")
    return 0 if n else 1


def cmd_supervisor(args) -> int:
    from . import recorder

    return recorder.supervisor_main(args.id, args.data_dir, args.adopt)


def register(sub) -> None:
    s = sub.add_parser("sources", help="list capture sources (* = default)")
    s.set_defaults(func=cmd_sources)
    s = sub.add_parser("record", help="start recording in the background")
    s.add_argument("--source", help="PipeWire node name (see: echo-app sources)")
    s.add_argument("--title", help="title for the recording")
    s.add_argument("--wait", action="store_true",
                   help="stay in the foreground, Ctrl+C stops; with --quick-note, wait for the text and print it")
    s.add_argument("--toggle", action="store_true", help="start a recording, or stop the active one")
    s.add_argument("--quick-note", action="store_true",
                   help="like --toggle, for a short note tagged 'nota' whose text is copied when ready")
    s.add_argument("--computer-audio", action=argparse.BooleanOptionalAction, default=None,
                   help="also record what the computer plays (a call's other side) as a second track; "
                        "default: as last chosen in the window")
    s.set_defaults(func=cmd_record)
    for name, fn, hlp in (("pause", cmd_pause, "pause the active recording"),
                          ("resume", cmd_resume, "resume the paused recording"),
                          ("stop", cmd_stop, "stop and save the active recording"),
                          ("status", cmd_status, "show the active recording")):
        s = sub.add_parser(name, help=hlp)
        s.set_defaults(func=fn)
    s = sub.add_parser("mark", help="add a marker to the active recording at the current time")
    s.add_argument("--note", help="a short note for the marker")
    s.set_defaults(func=cmd_mark)
    s = sub.add_parser("markers", help="list a recording's markers")
    s.add_argument("id")
    s.set_defaults(func=cmd_markers)
    s = sub.add_parser("recover", help="repair recordings interrupted by a crash")
    s.set_defaults(func=cmd_recover)
    s = sub.add_parser("finalize", help="retry saving a recording whose raw audio was kept")
    s.add_argument("id")
    s.set_defaults(func=cmd_finalize)
    s = sub.add_parser("import", help="import audio or video files, or folders (a video gives its sound)")
    s.add_argument("paths", nargs="*")
    s.add_argument("--no-transcribe", action="store_true", help="do not queue transcription")
    s.add_argument("--watch", action="store_true",
                   help="keep importing new files that appear in the folders (default: the watched folders in settings)")
    s.add_argument("--interval", type=float, default=30.0, help="seconds between looks at the folders (--watch)")
    s.set_defaults(func=cmd_import)
    s = sub.add_parser("_recorder")  # internal: the supervisor process
    s.add_argument("id")
    s.add_argument("--data-dir", required=True)
    s.add_argument("--adopt", action="store_true")
    s.set_defaults(func=cmd_supervisor)


cli_ext.REGISTRARS.append(register)
