# command-line Specification

## Purpose
The scripted interface: what `echo-app` accepts, prints and returns when a script or an AI
agent drives it without the window.

## Requirements

### Requirement: Transcribe files in one command
`echo-app transcribe` SHALL accept recording ids and paths to audio files, video files and
folders in one list. Paths SHALL be imported first; a path already in the library SHALL resolve
to its existing recording. An input that is neither SHALL be reported and nothing SHALL be
queued.

#### Scenario: A meeting video straight to text
- **WHEN** an agent runs `echo-app transcribe meeting.mp4 --format md`
- **THEN** the video's audio is imported, transcribed, and the Markdown transcript with speaker names is the only thing on standard output

### Requirement: Safe to repeat
`transcribe` SHALL NOT queue a recording again whose transcript is done, queued or running,
unless `--again` is given; it SHALL wait for or return the existing result instead.

#### Scenario: Rerun after a timeout
- **WHEN** `echo-app transcribe meeting.mp4 --format md --timeout 300` exits with code 3 and is run again
- **THEN** nothing is imported or queued again and the second run waits for the same job and prints its transcript

### Requirement: Transcript output
`--format txt|md|srt|vtt|json` SHALL wait for the transcripts and write them: to standard output
for one input without `--out`, to the file `--out PATH` for one input, and into the folder
`--out FOLDER` as one file per recording for several inputs. Several inputs with `--format` and
no `--out` SHALL be a usage error.

#### Scenario: A folder of meetings
- **WHEN** `echo-app transcribe ~/Videos/meetings --format md --out ~/notes` runs
- **THEN** each meeting becomes one Markdown file in `~/notes`

### Requirement: Machine-readable results
`transcribe`, `list` and `info` SHALL print one JSON document on standard output with `--json`.
Recordings SHALL have the same keys in every command, including id, title, duration, transcript
status, progress, error, speakers and the absolute paths of the recording's files. Keys SHALL be
added in later versions but never renamed or removed.

#### Scenario: Ask about one recording
- **WHEN** `echo-app info ID --json` runs while the recording is being transcribed
- **THEN** the output is valid JSON with `transcript_status` "running" and a progress fraction and time left

### Requirement: Progress and output streams
Standard output SHALL carry only results. Progress SHALL go to standard error: a redrawn line on
a terminal, otherwise one line per stage change and per further 10%.

#### Scenario: Progress in a captured shell
- **WHEN** an agent runs a 40-minute transcription with output captured
- **THEN** standard error holds a few dozen progress lines at most and standard output only the result

### Requirement: Bounded waiting and exit codes
`--timeout SECONDS` SHALL stop waiting after that time without cancelling the job. The exit code
SHALL be 0 when every input is done, 1 when any input failed, was rejected or not found or
transcription is not installed, 2 for usage errors, and 3 when the wait timed out with jobs still
queued or running.

#### Scenario: Tool call limit
- **WHEN** `--timeout 540` passes before the transcript is ready
- **THEN** the command exits with code 3, says to run it again, and the transcription continues

### Requirement: Headless and non-interactive
The scripted commands SHALL never open a window, prompt, or load Qt, and SHALL work without a
display. When transcription or its models are missing, `transcribe` SHALL fail before importing
anything, naming the command that fixes it.

#### Scenario: Over SSH
- **WHEN** `echo-app transcribe call.m4a --format txt` runs in an SSH session with no display
- **THEN** it prints the transcript and no Qt library is loaded

### Requirement: Learnable from help
`echo-app transcribe --help` SHALL show examples for one file, a folder, and waiting with a
timeout, and SHALL list the exit codes.

#### Scenario: An agent's first look
- **WHEN** an agent runs `echo-app transcribe --help`
- **THEN** it can build a working command and interpret its exit code from that text alone

### Requirement: Search by speaker from the command line
`echo-app list` SHALL accept `@name` in its query with the same meaning as in the window.

#### Scenario: An agent looks for what Ana said
- **WHEN** a script runs `echo-app list "@ana precio" --json`
- **THEN** only the recordings where Ana said "precio" are listed
