# Design

## Context

`cli_tr.cmd_transcribe` takes ids (or `--all`), calls `transcription.request` for each, and
with `--wait` polls `Recording.transcript_status()` every 0.5 s, drawing a `\r` progress line
only when standard output is a terminal. `transcription.request` always writes a new
`transcribe.requested`, so a second call on a finished recording transcribes it again.
`export.render_transcript(rec, fmt)` already renders txt, md, srt, vtt and json with speaker
names. The worker is a detached process started by `transcription.ensure_worker`; it never
needs a display. Speeds recorded in `~/.local/state/echo/speed.json` give a time left.

## Goals and non-goals

Goals: one command from a meeting file to its transcript; every command safe to rerun; output an
agent can parse without guessing; never block a tool call for longer than asked. Non-goals: a
long-running server, an MCP endpoint, new transcript formats.

## Decisions

### Inputs: ids and paths in one list

Each positional argument of `transcribe` is a recording id if `Library.get` finds one, else a
path if it exists, else an error ("no recording or file X", exit 1 before anything is queued).
Paths go through `importer.import_paths(..., auto_transcribe=False)`; `IMPORTED` and
`DUPLICATE` results both give a recording, `REJECTED` is reported and counts as a failure of
that input. Folders are accepted like `import` accepts them.

### Idempotency

`transcribe` skips recordings whose `transcript_status()` is `done`, `queued` or `running`, and
waits for them like the others. `--again` restores today's behavior for ids (a new run). This
changes what `echo-app transcribe ID` does for a finished recording; the window's own
"Transcribe again" is unaffected, and the old behavior was a footgun for scripts. Combined with
duplicate detection on import, rerunning `echo-app transcribe meeting.mp4 --format md` after a
timeout imports nothing, queues nothing, and waits for the same job.

### Output

- `--format FMT` implies `--wait`. With one input and no `--out`, the transcript goes to
  standard output; `--out PATH` writes a file (suffix from the format). With several inputs,
  `--out` must be a folder (created if missing) and each transcript is written as
  named by `export.suggested_name`, the same name the window's export dialog proposes; without `--out` that is a
  usage error, because concatenated SRT or JSON is not valid SRT or JSON.
- `--json` prints one JSON object when the command ends:
  `{"recordings": [{"input", "id", "title", "duration", "status", "error", "transcript"}]}`,
  where `transcript` is the path written with `--out` or null. `--json` and `--format` without
  `--out` would both claim standard output, so that combination is a usage error.
- `info ID --json` and `list --json` print the same record shape (one object, and
  `{"recordings": [...]}` respectively), built by one function so the keys cannot drift:
  `id, title, created, duration, source, extracted_from, state, transcript_status, progress
  {stage, fraction, eta_s}, error, language, speakers {count, names}, tags, folder, audio,
  files {transcript, edited, corrected}`. Paths are absolute. Keys are added, never renamed.
- Without `--json`, the human text stays as it is today.

### Progress on standard error

On a terminal: today's redrawn line, moved from stdout to stderr. Otherwise: one line when the
stage changes (`queued`, then the worker's `loading`, `detecting`, `transcribing`, `speakers`, then `done`) and every further
10%, prefixed with the recording id, for example
`2026-09-23T15-02-29_ab12 transcribing 40% (1:10 left)`. A 40-minute job prints about a dozen
lines, which fits an agent's context. Nothing else is written to stderr unless `-v`.

### Waiting with a limit

`--timeout SECONDS` is checked in the poll loop. When it passes, the command prints (stderr)
"still transcribing; run the same command again to keep waiting", prints the `--json` result
with `status` "running" if asked, and exits 3. The job is not cancelled: the worker is a
separate process and keeps going. Without `--timeout` the wait is unbounded, as today.

### Exit codes

0 every input done; 1 any input failed, was rejected or not found, or transcription/models are
missing; 2 usage error (argparse already uses 2); 3 timed out with jobs still queued or running
and none failed. Listed in `transcribe --help` and the README.

### Pre-flight

Before importing or queueing, `transcribe` checks `features.transcription_installed()` and
`models.all_cached()` and fails with the exact command (`./install.sh --with-transcription`,
`echo-app models download`). The worker would otherwise fail every job one by one.

### Headless

The commands import nothing from `ui/` and never Qt; a test runs `transcribe`, `info` and
`list` in a subprocess with `DISPLAY`, `WAYLAND_DISPLAY` and `QT_QPA_PLATFORM` unset and checks
that `PySide6` was never imported. `echo-app FILE` with no command still opens the window, as
desktop "Open with" needs; the README tells agents to use `transcribe`.

### Documentation for agents

`transcribe --help` gets an epilog with three examples (one file to Markdown on stdout, a folder
to an output folder, `--timeout` and rerun) and the exit codes. The README gains "Using Echo
from scripts and AI agents" with the same recipes and the `info --json` shape. No separate skill
or agent file: `--help` is what every agent reads first.

## Risks

- **Changed behavior of `transcribe ID` on a finished recording** for anyone scripting it today.
  Mentioned in the CHANGELOG; `--again` is the replacement.
- **Two clients waiting on one job** (the window and an agent): both only read files the worker
  writes, so both see the same progress and result.

## Decisions made while implementing

- **`transcribe --json` nests the recording.** Each input is
  `{"input", "result", "error", "output", "recording"}`, where `recording` is the same
  dictionary `info --json` prints (null for a file that was not imported). Flattening the
  recording's keys into the entry, as first sketched, would have given `transcribe` a different
  shape from `list` and `info`, which the spec forbids. `result` is the transcript status, or
  `rejected` and `failed` for inputs that never got that far.
- **`notes` is in the record**, next to `tags`: both are the user's own words about a recording.
- **`list --json`** prints `{"recordings": [...], "sets": [{"id", "title", "members"}]}` with
  the sets that contain a listed recording, so the sets stay visible without changing the
  recording shape.
- **Ids are tried only for bare names.** An input with a path separator is never looked up as a
  recording id, so `Library.get` cannot be pointed outside the recordings folder.
- **One recording given twice** (by id and by its file) is one job and one result.
- **Notes when stdout is the result.** With `--format` or `--json`, the human lines ("Imported",
  "Queued", "Already transcribed", "Done", "Saved") go to standard error; without them they stay
  on standard output as before, where they are the result.
- **Tests run the real worker loop** with the stub engine in a thread (`FakeWorker`), so the
  command's polling, progress and output are exercised end to end without a GPU.
