# Minutes and action items on the command line

## Why

Minutes and action items leave Echo through whatever the user runs: a cron sync, an agent that
loads items into the team's tracker, a script. Version 1 only printed a summary; nothing read
the items, and nothing listed what was recorded today.

## What Changes

- `echo-app meetings [--since] [--until] [--all] [--json]`: recordings with minutes, newest first.
- `echo-app minutes ID… [--json]`: the summary and the action items, each with its context and
  what was said around its time.
- `echo-app actions [ID…] [--since] [--until] [--owner] [--discarded] [--json]`: items across
  recordings.
- A skill in `agents/echo/` tells an agent how to read them.

## Capabilities

### New Capabilities

- `studio-data`

## Impact

`src/echo_studio/data.py` (new), `cli.py`; `agents/echo/SKILL.md` (new); `tests/test_studio.py`;
`docs/guide.md`.
