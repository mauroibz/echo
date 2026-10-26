"""Transcription and model commands."""

from __future__ import annotations

import sys
import time

from . import cli_ext


def _lib():
    from .library import Library
    from .settings import load

    cfg, _ = load()
    return cfg, Library(cfg.data_path)


# Exit codes, for scripts and agents (also in `transcribe --help`).
OK, FAILED, USAGE, TIMED_OUT = 0, 1, 2, 3


def _err(*a) -> None:
    print(*a, file=sys.stderr)


def _clock(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


class _Progress:
    """Progress on standard error: one redrawn line on a terminal; otherwise a line when a
    recording changes stage and at each further 10%, so a captured log stays a dozen lines."""

    def __init__(self):
        self.tty = sys.stderr.isatty()
        self.seen: dict[str, tuple[str, int]] = {}
        self.line = ""

    def clear(self) -> None:
        if self.tty and self.line:
            sys.stderr.write("\r" + " " * len(self.line) + "\r")
            sys.stderr.flush()
            self.line = ""

    def show(self, rec, stage: str, frac: float | None = None, eta: float | None = None) -> None:
        left = f", {_clock(eta)} left" if eta is not None else ""
        pct = f" {frac:.0%}" if frac is not None else ""
        if self.tty:
            line = f"  {rec.meta.title[:40]}: {stage}{pct}{left}"
            sys.stderr.write("\r" + line.ljust(len(self.line)))
            sys.stderr.flush()
            self.line = line
            return
        step = int((frac or 0) * 10)
        prev = self.seen.get(rec.id)
        if prev and prev[0] == stage and step <= prev[1]:
            return
        self.seen[rec.id] = (stage, step)
        _err(f"{rec.id} {stage}{pct}{left}")


def _resolve(lib, inputs: list[str]) -> tuple[list[tuple[str, object]], list[str], list[str]]:
    """Inputs as (input, recording id) and paths to import; plus the inputs that are neither.

    A bare name is tried as a recording id first; anything else that exists is a file or folder.
    """
    from pathlib import Path

    ids, paths, missing = [], [], []
    for item in inputs:
        rec = lib.get(item) if item and "/" not in item and "\\" not in item and item not in (".", "..") else None
        if rec is not None:
            ids.append((item, rec))
        elif Path(item).expanduser().exists():
            paths.append(item)
        else:
            missing.append(item)
    return ids, paths, missing


def _write_transcripts(recs, fmt: str, out, several: bool) -> dict[str, str]:
    """Write finished transcripts; returns {recording id: path written} ("-" for stdout)."""
    from pathlib import Path

    from . import export

    written = {}
    for rec in recs:
        text = export.render_transcript(rec, fmt)
        if out is None:
            sys.stdout.write(text)
            sys.stdout.flush()
            written[rec.id] = "-"
            continue
        dest = Path(out).expanduser()
        if several or dest.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            dest = dest / export.suggested_name(rec, fmt)
        elif dest.suffix.lower() != fmt:
            dest = dest.with_suffix(fmt)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        written[rec.id] = str(dest.resolve())
    return written


def cmd_transcribe(args) -> int:
    import json
    from pathlib import Path

    from . import cli_json, features, importer, models, transcription
    from .library import READY, T_DONE, T_FAILED, T_QUEUED, T_RUNNING

    fmt = "." + args.format if args.format else None
    wait = args.wait or fmt is not None or args.timeout is not None
    several = args.all or len(args.ids) > 1 or any(Path(i).expanduser().is_dir() for i in args.ids)
    if not args.all and not args.ids:
        _err("Give recording ids, audio or video files, or folders (or --all).")
        return USAGE
    if fmt and several and not args.out:
        _err("Several recordings need --out FOLDER with --format: one file per recording.")
        return USAGE
    if args.json and fmt and not args.out:
        _err("--json and --format both write to standard output; add --out.")
        return USAGE
    # Plain runs print their results on stdout; with a transcript or JSON there, notes go to stderr.
    say = _err if (args.json or fmt) else print

    if not features.transcription_installed():
        _err("Transcription is not installed. Run: ./install.sh --with-transcription")
        return FAILED
    if not models.all_cached():
        _err("The transcription models are not downloaded. Run: echo-app models download")
        return FAILED
    cfg, lib = _lib()

    entries: list[dict] = []  # one per input: {"input", "result", "error", "output", "rec"}
    if args.all:
        entries = [{"input": r.id, "rec": r} for r in lib.all()
                   if r.meta.state == READY and r.transcript_status() not in (T_DONE, T_QUEUED, T_RUNNING)]
    else:
        ids, paths, missing = _resolve(lib, args.ids)
        if missing:
            for m in missing:
                _err(f"No recording or file {m}")
            return FAILED
        order = {item: k for k, item in enumerate(args.ids)}
        found = [{"input": item, "rec": rec, "_at": order[item]} for item, rec in ids]
        if paths:
            importer.clean_staging(lib)
            for item in paths:
                for r in importer.import_paths(lib, [Path(item).expanduser()], auto_transcribe=False):
                    e = {"input": item if r.source == Path(item).expanduser() else str(r.source),
                         "rec": r.recording, "_at": order[item]}
                    if r.status == importer.REJECTED:
                        e.update(rec=None, result="rejected", error=r.message)
                        _err(f"Not imported {r.source}: {r.message}")
                    elif r.status == importer.IMPORTED:
                        say(f"Imported {r.source.name} as {r.recording.id}")
                    found.append(e)
        found.sort(key=lambda e: e.pop("_at"))  # stable: a folder's files stay in their order
        seen = set()
        for e in found:  # the same recording given twice (by id and by file) is one job
            if e["rec"] is None or e["rec"].id not in seen:
                entries.append(e)
                if e["rec"] is not None:
                    seen.add(e["rec"].id)
    if not entries:
        say("Nothing to transcribe.")
        return OK

    adapter = False if args.no_adapter else cfg.use_adapter
    queued_any = False
    for e in entries:
        r = e["rec"]
        if r is None:
            continue
        if r.meta.state != READY:
            e.update(result="failed", error=f"not ready ({r.meta.state})")
            _err(f"Skipping {r.id}: not ready ({r.meta.state})")
            continue
        status = r.transcript_status()
        if status in (T_DONE, T_QUEUED, T_RUNNING) and not args.again:
            say(f"{'Already transcribed' if status == T_DONE else 'Already ' + status} {r.id}  {r.meta.title}")
            continue
        if args.language:
            r.update(language=args.language)
        transcription.request(lib, r, adapter=adapter, context=args.context, start_worker=False)
        queued_any = True
        say(f"Queued {r.id}  {r.meta.title}")
    pending = {e["rec"].id: e["rec"] for e in entries if e["rec"] is not None and "result" not in e}
    if queued_any or (wait and pending):
        transcription.ensure_worker(lib)

    timed_out = False
    if wait:
        import time

        prog = _Progress()
        deadline = time.monotonic() + args.timeout if args.timeout is not None else None
        while pending:
            for rid, r in list(pending.items()):
                st = r.transcript_status()
                if st in (T_DONE, T_FAILED):
                    prog.clear()
                    if st == T_DONE:
                        t = r.transcript() or {}
                        say(f"Done {rid}  ({t.get('elapsed_s', '?')} s for {t.get('duration', 0):.0f} s of audio)")
                        if not prog.tty and say is not _err:  # the progress log's last line
                            _err(f"{rid} done")
                    else:
                        _err(f"Failed {rid}: {r.error_text()}")
                    del pending[rid]
                elif st == T_RUNNING:
                    p = cli_json.progress_of(r)
                    if p:
                        prog.show(r, p["stage"], p["fraction"], p["eta_s"])
                else:
                    prog.show(r, st)
            if not pending:
                break
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            if not transcription.worker_running(lib):
                time.sleep(1)
                if not transcription.worker_running(lib) and all(
                        r.transcript_status() == T_QUEUED for r in pending.values()):
                    transcription.ensure_worker(lib)
            time.sleep(0.5)
        prog.clear()
        if timed_out:
            _err(f"Still transcribing {len(pending)} recording(s); run the same command again to keep waiting.")

    for e in entries:
        r = e["rec"]
        if r is not None and "result" not in e:
            st = r.transcript_status()
            e["result"] = st
            if st == T_FAILED:
                e["error"] = r.error_text()
    done = [e["rec"] for e in entries if e.get("result") == T_DONE]
    if fmt and done:
        written = _write_transcripts(done, fmt, args.out, several)
        for e in entries:
            if e["rec"] is not None and e["rec"].id in written and written[e["rec"].id] != "-":
                e["output"] = written[e["rec"].id]
                say(f"Saved {e['output']}")

    if args.json:
        out = [{"input": e["input"], "result": e["result"], "error": e.get("error"), "output": e.get("output"),
                "recording": cli_json.record(e["rec"]) if e["rec"] is not None else None} for e in entries]
        print(json.dumps({"recordings": out}, ensure_ascii=False, indent=2))
    if any(e["result"] in ("rejected", "failed", T_FAILED) for e in entries):
        return FAILED
    if timed_out:
        return TIMED_OUT
    return OK


def cmd_info(args) -> int:
    import json

    from . import cli_json

    _, lib = _lib()
    rec = lib.get(args.id) if "/" not in args.id else None
    if rec is None:
        _err(f"No recording {args.id}")
        return FAILED
    d = cli_json.record(rec)
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return OK
    rows = [("Title", d["title"]), ("Created", d["created"]),
            ("Length", _clock(d["duration"]) if d["duration"] else "unknown"), ("Source", d["source"] or "-")]
    if d["tracks"]:
        rows.append(("Tracks", "channel 1 microphone, channel 2 computer audio"))
    if d["extracted_from"]:
        rows.append(("From video", f"{d['extracted_from']['name']} (sound {d['extracted_from']['method']})"))
    status = d["transcript_status"]
    if d["progress"]:
        p = d["progress"]
        left = f", {_clock(p['eta_s'])} left" if p["eta_s"] is not None else ""
        status += f" ({p['stage']} {p['fraction']:.0%}{left})"
    rows += [("Transcript", status), ("Language", d["language"])]
    if d["error"]:
        rows.append(("Error", d["error"]))
    if d["speakers"]:
        rows.append(("Speakers", ", ".join(d["speakers"]["names"])))
    if d["tags"]:
        rows.append(("Tags", " ".join(f"#{t}" for t in d["tags"])))
    rows += [("Folder", d["folder"]), ("Audio", d["audio"] or "-")]
    for name, path in d["files"].items():
        if path:
            rows.append((name.capitalize(), path))
    for k, v in rows:
        print(f"{k + ':':<12}{v}")
    return OK


def cmd_cancel(args) -> int:
    _, lib = _lib()
    r = lib.get(args.id)
    if r is None:
        print(f"No recording {args.id}", file=sys.stderr)
        return 1
    r.cancel_transcription()
    print("Cancelled.")
    return 0


def cmd_models(args) -> int:
    from . import features, models

    if args.action == "status":
        for ref in (*models.ALL, *models.OPTIONAL):
            state = "downloaded" if models.is_cached(ref) else "missing"
            note = "  (optional: who speaks)" if ref in models.OPTIONAL else ""
            print(f"{ref.repo}@{ref.revision[:10]}  {state}{note}")
        return 0 if models.all_cached() else 1
    if not features.transcription_installed():
        print("Transcription is not installed. Run: ./install.sh --with-transcription", file=sys.stderr)
        return 1
    gated_missing = not models.all_cached()
    if not models.missing():
        print("Models ready.")
        return 0
    if gated_missing and not models.hf_token_present():
        print("The models are gated on Hugging Face. Accept the terms on both model pages:\n"
              f"  https://huggingface.co/{models.BASE.repo}\n  https://huggingface.co/{models.ADAPTER.repo}\n"
              "then log in with: hf auth login", file=sys.stderr)
        return 1
    try:
        models.download(progress=print)
    except Exception as e:  # noqa: BLE001 - surface any hub error to the user
        print(f"Download failed: {e}", file=sys.stderr)
        if "401" in str(e) or "403" in str(e) or "gated" in str(e).lower():
            print("Make sure you accepted the terms on both model pages and are logged in.", file=sys.stderr)
        return 1
    print("Models ready.")
    return 0


def cmd_worker(args) -> int:
    from .worker.service import main

    return main(args.data_dir, args.idle_minutes)


def models_languages():
    from . import models

    return models.supported_languages()


def register(sub) -> None:
    import argparse

    s = sub.add_parser(
        "transcribe", help="transcribe recordings, or audio and video files (imported first)",
        description="Transcribe recordings by id, or audio and video files and folders, which are imported "
                    "first (a file already in the library is its existing recording). A recording that is "
                    "transcribed, queued or running is not queued again unless --again is given, so the same "
                    "command can be repeated safely. Results go to standard output, progress to standard error.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  echo-app transcribe meeting.mp4 --format md
      import a meeting video, wait, and print its transcript (with speakers) as Markdown
  echo-app transcribe ~/Videos/meetings --format txt --out ~/notes
      one text file per recording in ~/notes
  echo-app transcribe meeting.mp4 --format md --timeout 540
      stop waiting after 9 minutes with exit code 3; the job goes on, and running the same
      command again keeps waiting for it
  echo-app transcribe call.m4a --json
      queue it and print the recording as JSON (see: echo-app info ID --json)

exit codes:
  0  every recording is transcribed (or was queued, without waiting)
  1  a recording failed, a file was not imported or not found, or transcription is not installed
  2  usage error
  3  --timeout passed while transcription was still queued or running (nothing failed)""")
    s.add_argument("ids", nargs="*", metavar="ID|FILE|FOLDER",
                   help="recording ids (see: echo-app list), or audio and video files and folders")
    s.add_argument("--all", action="store_true", help="every recording without a transcript")
    s.add_argument("--wait", action="store_true", help="wait and show progress")
    s.add_argument("--again", action="store_true", help="transcribe again even if already transcribed")
    s.add_argument("--format", choices=["txt", "md", "srt", "vtt", "json"],
                   help="wait, then write the transcript in this format (standard output unless --out)")
    s.add_argument("--out", metavar="PATH",
                   help="with --format: the file to write, or a folder (one file per recording)")
    s.add_argument("--timeout", type=float, metavar="SECONDS",
                   help="wait at most this long, then exit with code 3 leaving the job running")
    s.add_argument("--json", action="store_true", help="print the result as JSON")
    s.add_argument("--no-adapter", action="store_true", help="use the base model without the Spanish adapter")
    s.add_argument("--language", metavar="CODE", choices=list(models_languages()),
                   help="language of the recording, remembered for it (es, en, pt, fr, it, de, ...)")
    s.add_argument("--context", metavar="TEXT",
                   help="who is speaking, what about (replaces the recording's own line for this run)")
    s.set_defaults(func=cmd_transcribe)
    s = sub.add_parser("info", help="show one recording: transcript state, progress, speakers, files")
    s.add_argument("id")
    s.add_argument("--json", action="store_true", help="print it as JSON (the keys of list --json)")
    s.set_defaults(func=cmd_info)
    s = sub.add_parser("cancel", help="cancel a queued or running transcription")
    s.add_argument("id")
    s.set_defaults(func=cmd_cancel)
    s = sub.add_parser("models", help="download or check the transcription models")
    s.add_argument("action", choices=["download", "status"])
    s.set_defaults(func=cmd_models)
    s = sub.add_parser("_worker")
    s.add_argument("--data-dir", required=True)
    s.add_argument("--idle-minutes", type=float)
    s.set_defaults(func=cmd_worker)


cli_ext.REGISTRARS.append(register)
