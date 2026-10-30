"""`echo-app summarize`: summaries from the command line, for scripts and agents."""

from __future__ import annotations

import json
import sys

from . import config, llm, summary, templates

# Exit codes, as Echo's transcribe: 0 done, 1 a recording failed, 2 usage, 3 no server set up.
OK, FAILED, USAGE, NOT_SET_UP = 0, 1, 2, 3


def _err(*a) -> None:
    print(*a, file=sys.stderr)


def cmd_summarize(args) -> int:
    from echo_app.cli_json import record
    from echo_app.library import Library
    from echo_app.settings import load

    cfg = config.load()
    if not cfg.enabled:
        _err("Summaries need a language-model server. Set one in Settings, Summaries, or write its "
             f"address (ending in /v1) and model name to {config.config_path()}:\n"
             '  llm_url = "http://127.0.0.1:8080/v1"\n  llm_model = "the-model-name"\n'
             "An API key, if the server needs one, goes in Settings (kept in the keyring) or "
             f"${config.KEY_ENV}.")
        return NOT_SET_UP
    lib = Library(load()[0].data_path)
    code = OK
    out = []
    if args.all == bool(args.ids):
        _err("give recording ids, or --all")
        return USAGE
    if args.template is not None and args.template != "general" and not templates.text(args.template):
        _err(f"no template “{args.template}”; there are: general, " + ", ".join(templates.names()))
        return USAGE
    ids = args.ids or [r.id for r in lib.all() if summary.source_text(r) and _needs(r)]
    if args.all:
        _err(f"{len(ids)} recording(s) to summarize")
    for rid in ids:
        rec = lib.get(rid)
        if rec is None:
            _err(f"{rid}: no such recording (see: echo-app list)")
            code = FAILED
            continue
        if args.template is not None:
            templates.set_for(rec, None if args.template == "general" else args.template)
        data = summary.load(rec)
        if data is not None and not args.force and not summary.stale(rec, data):
            _err(f"{rid}: already summarized (--force to do it again)")
        else:
            try:
                data = summary.write(rec, progress=lambda d, t: _err(f"{rid}: request {d + 1} of {t}")
                                     if t > 1 else _err(f"{rid}: summarizing…"), cfg=cfg)
            except (ValueError, llm.LLMError) as e:
                _err(f"{rid}: {e}")
                code = FAILED
                continue
            if cfg.auto_title:
                try:
                    if title := summary.retitle(rec, data, cfg):
                        _err(f"{rid}: titled “{title}”")
                except llm.LLMError as e:
                    _err(f"{rid}: no title: {e}")
        if args.json:
            d = record(rec)
            d["summary"] = {"path": str(rec.path(summary.FILE).resolve()), "created": data.get("created"),
                            "stale": summary.stale(rec, data), "text": data["text"]}
            out.append(d)
        elif args.print:
            print(data["text"] + "\n")
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return code


def _needs(rec) -> bool:
    data = summary.load(rec)
    return data is None or summary.stale(rec, data)


def register(sub) -> None:
    import argparse

    s = sub.add_parser(
        "summarize", help="summarize recordings with a language model (Echo Studio)",
        description="Summarize transcribed recordings with the OpenAI-compatible server set in Settings, "
                    "Summaries. A recording whose summary was made from its current text is not summarized "
                    "again unless --force is given. The summary is saved as summary.json in the recording's "
                    "folder; the transcript is sent to the server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  echo-app summarize 20261029-103000-ab12 --print
      summarize one recording and print the summary (Markdown)
  echo-app summarize --all
      summarize every transcribed recording that has no current summary
  echo-app summarize 20261029-103000-ab12 --json
      the recording as JSON (see: echo-app info ID --json) with a "summary" key

exit codes:
  0  every recording is summarized
  1  a recording was not found, has no transcript, or the server failed
  2  usage error
  3  no server is set up""")
    s.add_argument("ids", nargs="*", metavar="ID", help="recording ids (see: echo-app list)")
    s.add_argument("--all", action="store_true",
                   help="every transcribed recording whose summary is missing or out of date")
    s.add_argument("--template", metavar="NAME",
                   help="the kind of meeting (kept as the recording's template: tag); \"general\" for none. "
                        "Built in: " + ", ".join(sorted(templates.BUILT_IN)) + "; your own go in "
                        "~/.config/echo/studio/templates/NAME.md")
    s.add_argument("--force", action="store_true", help="summarize again even if the summary is current")
    s.add_argument("--print", action="store_true", help="print each summary to standard output")
    s.add_argument("--json", action="store_true", help="print the result as JSON")
    s.set_defaults(func=cmd_summarize)
