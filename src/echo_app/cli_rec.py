"""Recording commands: record, pause, resume, stop, status, sources, recover, finalize."""

from __future__ import annotations

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
    from .audio import pipewire

    sources = pipewire.list_sources()
    if not sources:
        print("No PipeWire sources found. Is PipeWire running?", file=sys.stderr)
        return 1
    for s in sources:
        mark = "*" if s.is_default and s.kind == pipewire.INPUT else " "
        print(f"{mark} {s.label}\n    {s.name}")
    return 0


def cmd_record(args) -> int:
    from . import recorder

    cfg, lib = _lib()
    recorder.recover_all(lib)
    try:
        sess = recorder.start(lib, source=args.source if args.source is not None else cfg.source,
                              rate=cfg.sample_rate, channels=cfg.channels, title=args.title)
    except recorder.RecorderError as e:
        print(e, file=sys.stderr)
        return 1
    st = sess.status()
    print(f"Recording \"{sess.rec.meta.title}\" from {sess.rec.meta.source or 'default input'}")
    print(f"  id: {sess.rec.id}")
    if not args.wait:
        print("Stop with: echo-app stop")
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

    _, lib = _lib()
    importer.clean_staging(lib)

    def progress(i, n, path):
        if path.name and sys.stdout.isatty():
            print(f"\r  [{i + 1}/{n}] {path.name[:60]:<60}", end="", flush=True)

    results = importer.import_paths(lib, [Path(p) for p in args.paths], progress=progress,
                                    auto_transcribe=None if not args.no_transcribe else False)
    if sys.stdout.isatty():
        print("\r" + " " * 72 + "\r", end="")
    if not results:
        print("No audio files found.", file=sys.stderr)
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
    s.add_argument("--wait", action="store_true", help="stay in the foreground; Ctrl+C stops")
    s.set_defaults(func=cmd_record)
    for name, fn, hlp in (("pause", cmd_pause, "pause the active recording"),
                          ("resume", cmd_resume, "resume the paused recording"),
                          ("stop", cmd_stop, "stop and save the active recording"),
                          ("status", cmd_status, "show the active recording")):
        s = sub.add_parser(name, help=hlp)
        s.set_defaults(func=fn)
    s = sub.add_parser("recover", help="repair recordings interrupted by a crash")
    s.set_defaults(func=cmd_recover)
    s = sub.add_parser("finalize", help="retry saving a recording whose raw audio was kept")
    s.add_argument("id")
    s.set_defaults(func=cmd_finalize)
    s = sub.add_parser("import", help="import audio files or folders")
    s.add_argument("paths", nargs="+")
    s.add_argument("--no-transcribe", action="store_true", help="do not queue transcription")
    s.set_defaults(func=cmd_import)
    s = sub.add_parser("_recorder")  # internal: the supervisor process
    s.add_argument("id")
    s.add_argument("--data-dir", required=True)
    s.add_argument("--adopt", action="store_true")
    s.set_defaults(func=cmd_supervisor)


cli_ext.REGISTRARS.append(register)
