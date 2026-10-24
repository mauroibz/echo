# Tasks

Depends on `add-video-import` (video paths). The reference recording is the same meeting video
named in that change's `tasks.md`; nothing from it goes into the repository.

## 1. Inputs and idempotency

- [ ] 1.1 `transcribe` resolves each input to a recording: id, file or folder (imported with `auto_transcribe=False`, duplicates resolve to the existing recording), else an error before anything is queued; tests with ids, an audio file, a generated video, a duplicate and a missing path
- [ ] 1.2 Skip done, queued and running recordings unless `--again`; tests that a second run writes no new `transcribe.requested`
- [ ] 1.3 Pre-flight for transcription and models before importing; tests with both missing

## 2. Waiting and output

- [ ] 2.1 Progress to stderr: redrawn on a TTY, otherwise per stage and per 10%; tests driving a stub worker's progress files and counting lines
- [ ] 2.2 `--timeout` with exit code 3 and the job left running; exit codes 0, 1, 2, 3 tested
- [ ] 2.3 `--format` (implies `--wait`) and `--out` file or folder, through `export.render_transcript`; the usage errors in the design; tests with the stub engine's transcript, including speaker names

## 3. JSON and info

- [ ] 3.1 One record-to-dict function; `info ID [--json]`, `list --json`, `transcribe --json`; tests parsing the output and checking the key set, so a renamed key fails the test
- [ ] 3.2 Headless test: subprocess with no display variables, `PySide6` not in `sys.modules` at exit, for `transcribe`, `info` and `list`

## 4. Help and docs

- [ ] 4.1 `transcribe --help` epilog with the three examples and the exit codes
- [ ] 4.2 README "Using Echo from scripts and AI agents" (recipes, `--timeout` and rerun, `info --json` keys, `--context` for names); `docs/design.md` command-line section; CHANGELOG, including the changed default of `transcribe ID` on a finished recording

## 5. Real run

- [ ] 5.1 From a shell with no display variables, run `echo-app transcribe <reference video> --format md --timeout 540` from a Claude Code session as an agent would; record in `docs/design.md` the wall time, the number of progress lines, and that a rerun printed the same transcript without queueing (needs hardware: the GPU and the reference video)
- [ ] 5.2 Fast suite passes; archive the change
