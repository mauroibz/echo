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


def cmd_transcribe(args) -> int:
    from . import features, transcription
    from .library import READY, T_DONE, T_FAILED

    if not features.transcription_installed():
        print("Transcription is not installed. Run: ./install.sh --with-transcription", file=sys.stderr)
        return 1
    cfg, lib = _lib()
    if args.all:
        recs = [r for r in lib.all() if r.meta.state == READY and r.transcript_status() not in (T_DONE,)]
    else:
        recs = []
        for rid in args.ids:
            r = lib.get(rid)
            if r is None:
                print(f"No recording {rid}", file=sys.stderr)
                return 1
            recs.append(r)
    if not recs:
        print("Nothing to transcribe.")
        return 0
    adapter = False if args.no_adapter else cfg.use_adapter
    for r in recs:
        if r.meta.state != READY:
            print(f"Skipping {r.id}: not ready ({r.meta.state})")
            continue
        transcription.request(lib, r, adapter=adapter)
        print(f"Queued {r.id}  {r.meta.title}")
    if not args.wait:
        return 0
    pending = {r.id: r for r in recs if r.meta.state == READY}
    failed = 0
    last_line = ""
    while pending:
        for rid, r in list(pending.items()):
            st = r.transcript_status()
            if st == T_DONE:
                t = r.transcript() or {}
                print(f"\r{' ' * len(last_line)}\rDone {rid}  ({t.get('elapsed_s', '?')} s for "
                      f"{t.get('duration', 0):.0f} s of audio)")
                del pending[rid]
            elif st == T_FAILED:
                print(f"\rFailed {rid}: {r.error_text()}", file=sys.stderr)
                failed += 1
                del pending[rid]
            else:
                p = r.progress()
                if p and sys.stdout.isatty():
                    frac = p["done"] / p["total"] if p.get("total") else 0
                    eta = f", {int(p['eta_s']) // 60}:{int(p['eta_s']) % 60:02d} left" if p.get("eta_s") is not None else ""
                    line = f"  {r.meta.title[:40]}: {p['stage']} {frac:.0%}{eta}"
                    print("\r" + line.ljust(len(last_line)), end="", flush=True)
                    last_line = line
        if not transcription.worker_running(lib) and pending:
            time.sleep(1)
            if not transcription.worker_running(lib) and all(r.transcript_status() == "queued" for r in pending.values()):
                transcription.ensure_worker(lib)
        time.sleep(0.5)
    return 1 if failed else 0


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
        for ref in models.ALL:
            state = "downloaded" if models.is_cached(ref) else "missing"
            print(f"{ref.repo}@{ref.revision[:10]}  {state}")
        return 0 if models.all_cached() else 1
    if not features.transcription_installed():
        print("Transcription is not installed. Run: ./install.sh --with-transcription", file=sys.stderr)
        return 1
    if not models.hf_token_present():
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


def register(sub) -> None:
    s = sub.add_parser("transcribe", help="queue recordings for transcription")
    s.add_argument("ids", nargs="*", help="recording ids (see: echo-app list)")
    s.add_argument("--all", action="store_true", help="every recording without a transcript")
    s.add_argument("--wait", action="store_true", help="wait and show progress")
    s.add_argument("--no-adapter", action="store_true", help="use the base model without the Spanish adapter")
    s.set_defaults(func=cmd_transcribe)
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
