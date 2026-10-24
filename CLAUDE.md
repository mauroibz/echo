# Working on Echo

Echo is a Linux desktop app that records long-form audio and transcribes Spanish speech
locally. `README.md` is for users, `docs/design.md` explains the architecture and its
reasons, `openspec/specs/` is the behavior each part must keep, and `docs/roadmap.md` is
the plan. This file is for an agent implementing that plan without anyone watching.

## Hard constraints

- No audio may ever be lost. Recording must survive window crashes, SIGKILL and power loss.
- Plain files are the truth; the SQLite index is a rebuildable cache.
- Lean and finished: few features done completely, no flags hiding unfinished work.
- Per-user install only. Never use the system Python. Dependencies are hash-locked with uv,
  wheels only, `no-build`; change `uv.lock` only with `uv lock`, never by hand. Model
  revisions are pinned in `src/echo_app/models.py` and are not changed by a feature.
- The window process never imports torch. Only `src/echo_app/worker/` does.
- A new dependency needs a sentence in the change's `design.md` saying why no existing one
  does the job, and a row in the "Packaging and dependency risk" table of `docs/design.md`.
- The CLI command is `echo-app` (`echo` is a shell builtin).
- Never put model names or session identifiers into code, commits or docs.

## Environment setup (verified in a cloud container, 2026-10-24)

```sh
# Ubuntu-based container; uv and ffmpeg were present, Qt's runtime libraries were not.
apt-get install -y libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3 libglib2.0-0 libxcb-cursor0
uv sync --locked --no-install-project           # base profile + pytest, ~10 s, no torch
QT_QPA_PLATFORM=offscreen uv run --no-sync pytest -q   # 100 passed, 4 skipped, ~1 min
```

The fast suite needs no GPU, microphone, PipeWire or model. Tests under `ECHO_PIPEWIRE_TESTS`
and `ECHO_MODEL_TESTS` need real hardware and are skipped otherwise. The `worker` extra
(torch, 3.5 GB) is not needed for the suite; `tests/test_worker.py` uses a stub engine.

## How to work a change

1. **Pick** the first change in the phase table of `docs/roadmap.md` whose folder is still in
   `openspec/changes/` (not `archive/`) and whose dependencies, listed under the table, are
   archived. Do one change per session unless told otherwise.
2. **Read** its `proposal.md`, `design.md` (if present), `specs/*/spec.md` and `tasks.md`, then
   the current specs it modifies in `openspec/specs/` and the code files its Impact section
   names. The design's decisions are final: do not reopen them, do not ask about them. Where
   the design is silent, choose the option closest to existing code and write the choice into
   `design.md` under a "Decisions made while implementing" heading.
3. **Implement** task by task, checking each `- [ ]` to `- [x]` as it is done and verified.
   Every task's verification is part of the task. Match the surrounding code: module
   docstring first, `from __future__ import annotations`, stdlib-only outside the worker and
   the UI, atomic writes through `fsutil`, lines up to about 110 characters, comments that
   say why and record measurements.
4. **Test.** Add tests next to the existing ones (`tests/test_*.py`; UI tests drive real
   widgets offscreen as in `tests/test_ui.py`; the recorder uses `tests/fake_capture.py`).
   The whole fast suite must pass before every commit.
5. **Document.** Update `README.md` for anything a user sees (features, shortcuts, settings,
   troubleshooting) and `docs/design.md` for anything about how it works. Add a line to
   `CHANGELOG.md` under Unreleased once that file exists (`add-ubuntu-parity` creates it).
6. **Archive.** When every task is done: merge the change's spec deltas into
   `openspec/specs/<capability>/spec.md` (ADDED requirements are appended; MODIFIED replace
   the requirement with the same heading; a new capability gets a new folder), then move the
   change folder to `openspec/changes/archive/<YYYY-MM-DD>-<name>/`. Update the phase table
   in `docs/roadmap.md` if the order or dependencies changed.
7. **Commit** in small steps with messages in the repository's style (imperative first line,
   a short body saying why), on the branch you were given, and push.

## Tasks that need hardware

Some tasks say "needs hardware" (a GPU, a microphone, a Windows or macOS machine). Do
everything else in the change first. Leave those tasks unchecked, add a `## Blocked` section
to `tasks.md` naming each one and exactly what a person must run and look for, do not archive
the change, and say so in the final commit message and summary. Never mark a verification done
that did not run, and never substitute a mocked result for a measurement.

## When to stop and ask

Stop only if a hard constraint above would have to be broken, a design decision turns out to
be impossible as written, or a change needs a secret or an account you do not have. Everything
else is yours to decide and record.
