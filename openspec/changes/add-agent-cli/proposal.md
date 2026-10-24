# Proposal

## Why

The main use for Echo is long meetings, and the transcripts are often read and worked on by an
AI agent (summaries, action items, minutes) rather than by a person in the window. An agent
drives programs through a shell: it needs one command that takes a file and gives back the
transcript, output it can parse, progress that does not fill its context, exit codes it can act
on, and commands it can safely run again after its own tool call timed out.

Today the pieces exist but do not fit together for that. `echo-app import` and
`echo-app transcribe ID --wait` are separate steps joined by an id that has to be read out of
human-formatted text; `--wait` shows progress only on a terminal, so an agent sees nothing for
the whole job; running `transcribe` again restarts a finished or running job; there is no way to
ask about one recording; and nothing is documented for scripted use.

## What Changes

- **`echo-app transcribe FILE`** accepts paths to audio or video files as well as recording ids.
  Files are imported first (video as its audio, through `add-video-import`); a file already in
  the library resolves to its existing recording.
- **Safe to repeat.** A recording that already has a transcript, or whose transcription is
  queued or running, is not queued again; `--again` asks for a new run. Running the same
  command twice waits for, or returns, the same result.
- **The transcript in one step.** `--format txt|md|srt|vtt|json` waits and writes the
  transcript, with speaker names, to standard output (or `--out PATH`; with several inputs,
  `--out FOLDER`, one file per recording).
- **Bounded waits.** `--timeout SECONDS` stops waiting after that long with exit code 3 and
  leaves the job running, so an agent whose tool calls are limited to a few minutes runs the
  same command again to keep waiting.
- **Machine-readable results.** `--json` on `transcribe`, `list` and the new `info` prints one
  JSON document on standard output with stable keys.
- **`echo-app info ID`**: one recording's title, date, length, source, transcript state,
  progress and time left, error, language, speakers, tags and the paths of its files.
- **Quiet, predictable output.** Standard output carries only the result. Progress goes to
  standard error: the redrawn line on a terminal, otherwise one line per stage and every 10%.
  Exit codes: 0 done, 1 failed or not found, 2 usage, 3 timed out (still running).
- **Headless.** None of these commands open a window, prompt, or load Qt; they work over SSH
  and with no display. Missing transcription or models fail at once with the exact command to
  fix it, before anything is imported.
- **Documented for agents.** A README section with the recipes, and `transcribe --help` listing
  examples and exit codes, so an agent can learn the tool from `--help` alone.

Out of scope: a server or API, MCP, transcribing linked sets as one job, summaries.

## Capabilities

### New Capabilities
- `command-line`: the scripted interface's inputs, outputs, idempotency, exit codes and
  headless behavior.

## Impact

`cli_tr.py` (`transcribe` inputs, `--again`, `--format`, `--out`, `--timeout`, `--json`,
progress to stderr; `info`); `cli.py` (`list --json`); `export.py` (reused as is for the
transcript formats); `importer.py` (used by `transcribe`; no change); a small `cli_json.py`
for the shared record-to-dict shape if `info` and `list` need it; `README.md`,
`docs/design.md`. Depends on `add-video-import`. No new dependencies.
