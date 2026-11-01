"""Studio on the command line, for scripts and agents: `summarize` uses the server; `meetings`,
`minutes` and `actions` only read what is saved (the way minutes and items leave Echo)."""

from __future__ import annotations

import json
import sys

from . import config, followup, keychain, llm, summary, templates

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
            for note in summary.finish(rec, data, cfg):
                _err(f"{rid}: {note}")
        if args.json:
            d = record(rec)
            d["summary"] = {"path": str(rec.path(summary.FILE).resolve()), "created": data.get("created"),
                            "stale": summary.stale(rec, data), "text": data["text"]}
            out.append(d)
        elif args.print:
            print(data["text"] + "\n")
        if args.follow_up:
            try:
                subject, body = followup.draft(rec, cfg)
            except (ValueError, llm.LLMError) as e:
                _err(f"{rid}: no follow-up: {e}")
                code = FAILED
                continue
            print(f"Subject: {subject}\n\n{body}\n")
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return code


def _library():
    from echo_app.library import Library
    from echo_app.settings import load

    return Library(load()[0].data_path)


def _bad_date(*values) -> str | None:
    from . import data

    for v in values:
        if v:
            try:
                data._day(v, end=False)
            except ValueError:
                return v
    return None


def cmd_meetings(args) -> int:
    from . import data, marks

    bad = _bad_date(args.since, args.until)
    if bad:
        _err(f"not a date: {bad} (YYYY-MM-DD, today or yesterday)")
        return USAGE
    lib = _library()
    recs = sorted((r for r in lib.all() if data.in_range(r, args.since, args.until)
                   and (args.all or summary.load(r) is not None)
                   and (not args.starred or marks.starred(r))), key=lambda r: r.meta.created, reverse=True)
    if args.json:
        print(json.dumps([data.meeting(r, full=False, lib=lib) for r in recs], ensure_ascii=False, indent=2))
        return OK
    for r in recs:
        n = len(data.action_items(r, lib=lib))
        tail = f"  ({n} action item{'s' if n != 1 else ''})" if summary.load(r) is not None else "  (no minutes)"
        star = "★ " if marks.starred(r) else ""
        print(f"{r.id}  {r.meta.created[:16].replace('T', ' ')}  {star}{r.meta.title}{tail}")
    return OK


def cmd_minutes(args) -> int:
    from . import data

    lib = _library()
    out, code = [], OK
    for rid in args.ids:
        rec = lib.get(rid)
        if rec is None:
            _err(f"{rid}: no such recording (see: echo-app meetings)")
            code = FAILED
            continue
        if summary.load(rec) is None:
            _err(f"{rid}: no minutes yet (see: echo-app summarize {rid})")
            code = FAILED
            continue
        m = data.meeting(rec, lib=lib)
        if args.json:
            out.append(m)
            continue
        print(f"# {rec.meta.title}\n\n{m['minutes']['text'].strip()}\n")
        if m["action_items"]:
            print("## Action items\n")
            for it in m["action_items"]:
                print(_item_line(it))
            print()
    if args.json:
        print(json.dumps(out[0] if len(args.ids) == 1 and out else out, ensure_ascii=False, indent=2))
    return code


def _item_line(it: dict) -> str:
    bits = [b for b in (it["owner"], f"by {it['due']}" if it["due"] else "", it["at_stamp"]) if b]
    line = f"- {it['text']}" + (f" ({', '.join(bits)})" if bits else "")
    for extra in (it["description"], f"Context: {it['context']}" if it["context"] else ""):
        if extra:
            line += f"\n  {extra}"
    return line  # the user's note stays out: it is theirs, not the tracker's (it is in --json)


def cmd_actions(args) -> int:
    from echo_app.library import fold_tag

    from . import data

    bad = _bad_date(args.since, args.until)
    if bad:
        _err(f"not a date: {bad} (YYYY-MM-DD, today or yesterday)")
        return USAGE
    lib = _library()
    if args.ids:
        recs = [lib.get(i) for i in args.ids]
        if any(r is None for r in recs):
            _err("no such recording: " + ", ".join(i for i, r in zip(args.ids, recs) if r is None))
            return FAILED
    else:
        recs = sorted((r for r in lib.all() if data.in_range(r, args.since, args.until)),
                      key=lambda r: r.meta.created, reverse=True)
    want = fold_tag(args.owner) if args.owner else None
    items = []
    for r in recs:
        for it in data.action_items(r, discarded=args.discarded, lib=lib):
            if want is None or fold_tag(it["owner"]) == want:
                items.append({**it, "title": r.meta.title, "created": r.meta.created})
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return OK
    last = None
    for it in items:
        if it["recording"] != last:
            print(("\n" if last else "") + f"{it['title']} ({it['recording']})")
            last = it["recording"]
        print(_item_line(it))
    return OK


def cmd_calendar(args) -> int:
    from datetime import datetime, timedelta

    from . import calendar

    if args.set:
        try:
            found = calendar.save_urls(sys.stdin.read())
        except keychain.KeychainError as e:
            _err(str(e))
            return FAILED
        _err(f"{len(found)} calendar address(es) kept in the keyring")
        args.refresh = bool(found)
    if not calendar.enabled():
        _err("No calendar set. Paste its private ICS address in Settings, Calendar, or pipe it to "
             f"echo-app calendar --set; ${calendar.URLS_ENV} also works.")
        return NOT_SET_UP
    if args.refresh:
        errors = calendar.refresh()
        for e in errors:
            _err(e)
        if errors and len(errors) == len(calendar.urls()):
            return FAILED
    now = datetime.now().astimezone()
    evs = [e for e in calendar.events(now, now + timedelta(days=args.days)) if e.end > now]
    if args.json:
        print(json.dumps([e.as_dict() for e in evs], ensure_ascii=False, indent=2))
        return OK
    for e in evs:
        when = "all day" if e.all_day else f"{e.start:%H:%M}-{e.end:%H:%M}"
        names = ", ".join(a.name or a.email for a in e.attendees[:4]) + ("…" if len(e.attendees) > 4 else "")
        print(f"{e.start:%a %b %d}  {when:11}  {e.title}" + ("  [video]" if e.link else "")
              + (f"  ({names})" if names else ""))
    return OK


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
    s.add_argument("--follow-up", action="store_true",
                   help="print a follow-up email drafted from the summary (Studio sends nothing)")
    s.add_argument("--print", action="store_true", help="print each summary to standard output")
    s.add_argument("--json", action="store_true", help="print the result as JSON")
    s.set_defaults(func=cmd_summarize)

    keys = ("JSON keys are only ever added, never renamed or removed, so a sync can rely on them. Reads what "
            "is saved; sends nothing.")
    m = sub.add_parser(
        "meetings", help="list recordings with minutes, newest first (Echo Studio)",
        description="Recordings that have minutes (a summary), newest first. " + keys,
        epilog="""examples:
  echo-app meetings --since today
  echo-app meetings --since 2026-10-01 --until 2026-10-31 --json""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    m.add_argument("--since", metavar="DATE", help="made on or after this day (YYYY-MM-DD, today, yesterday)")
    m.add_argument("--until", metavar="DATE", help="made on or before this day")
    m.add_argument("--all", action="store_true", help="also recordings without minutes")
    m.add_argument("--starred", action="store_true", help="only the meetings you starred")
    m.add_argument("--json", action="store_true", help="as JSON: each recording (as info --json) with "
                   "\"minutes\" (created, stale, template, excerpt), \"starred\" and the number of \"action_items\"")
    m.set_defaults(func=cmd_meetings)

    n = sub.add_parser(
        "minutes", help="a recording's minutes and action items (Echo Studio)",
        description="The summary and the action items (not the discarded ones) of each recording. " + keys,
        epilog="""JSON: the recording (as info --json) with "minutes" {path, created, stale, template, excerpt, text}
and "action_items", each {index, text, description, owner, owner_email, due, at, at_stamp, context,
note, edited, added_by_user, quote, recording}; "description" is what exactly and why, as said;
"context" is the user's, for whoever picks the item up; "note" is the user's own and not meant for
a tracker; "quote" is what was said around the item's time. One ID gives one object,
several give a list.

examples:
  echo-app minutes 20261031-110000-ab12
  echo-app minutes 20261031-110000-ab12 --json""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    n.add_argument("ids", nargs="+", metavar="ID")
    n.add_argument("--json", action="store_true", help="as JSON")
    n.set_defaults(func=cmd_minutes)

    t = sub.add_parser(
        "actions", help="action items across recordings, newest first (Echo Studio)",
        description="Action items as polished in the minutes, newest recording first; discarded ones are left "
                    "out. Echo does not track whether they got done. " + keys,
        epilog="""examples:
  echo-app actions --since today --json
  echo-app actions 20261031-110000-ab12
  echo-app actions --owner "Sofía Paz" --since 2026-10-01""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    t.add_argument("ids", nargs="*", metavar="ID", help="these recordings only")
    t.add_argument("--since", metavar="DATE", help="recordings made on or after this day")
    t.add_argument("--until", metavar="DATE", help="recordings made on or before this day")
    t.add_argument("--owner", metavar="NAME", help="one person's items")
    t.add_argument("--discarded", action="store_true", help="include the discarded ones")
    t.add_argument("--json", action="store_true", help="as JSON: the items as in minutes --json, with the "
                   "recording's \"title\" and \"created\"")
    t.set_defaults(func=cmd_actions)

    c = sub.add_parser(
        "calendar", help="the meetings in your calendar (Echo Studio)",
        description="The events in the calendars whose private ICS addresses are set (Settings, Calendar), "
                    "from the copy fetched last; --refresh fetches them first. Echo only reads calendars.",
        epilog="""examples:
  echo-app calendar --refresh
  echo-app calendar --days 7 --json
  echo-app calendar --set < addresses.txt      one address per line, kept in the keyring

exit codes: 0 listed, 1 no calendar could be fetched, 3 no calendar set""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    c.add_argument("--days", type=float, default=1, help="how far ahead (default 1)")
    c.add_argument("--refresh", action="store_true", help="fetch the calendars first")
    c.add_argument("--set", action="store_true", help="read the addresses from standard input and keep them")
    c.add_argument("--json", action="store_true", help="as JSON: each event with its attendees' emails")
    c.set_defaults(func=cmd_calendar)

