# Echo

Record long-form audio and transcribe Spanish speech locally, on your own GPU.

![Echo with a recording selected: recorder and library on the left, waveform with crop and the transcript on the right](docs/screenshot.png)

Echo is a desktop app for Linux with PipeWire. It records from any input (or from what the
computer is playing), imports audio from anywhere including WhatsApp voice notes, and
transcribes Spanish with [Cohere Transcribe](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026)
and the [Surus Spanish adapter](https://huggingface.co/surus-ai/cohere-transcribe-spanish-MegaASR).
After the one-time model download nothing leaves the machine.

What it is built around:

- **No lost audio.** Recording runs in its own background process and is flushed to disk every
  two seconds. Closing the window, a crash, killing the recorder or a power cut loses nothing
  that reached the disk; the next start recovers the recording automatically. The finished
  file is lossless FLAC, kept only after it is verified to decode to exactly the captured audio.
- **Long recordings.** Speech detection splits audio into passages of up to 28 seconds at
  natural pauses, so hours of stream-of-consciousness talk transcribe with paragraph breaks and
  timing. An RTX 3080 transcribes about 70 minutes of audio per minute.
- **Your edits are safe.** The model transcript and your edited text are stored separately.
  Transcribing again never overwrites your edits.
- **Plain files.** Every recording is a folder with its audio, a `meta.json` and its
  transcripts. Nothing is hidden in a database you depend on.

## Install

Requirements: Linux with PipeWire, `ffmpeg`, and [`uv`](https://docs.astral.sh/uv/).
On Fedora:

```sh
sudo dnf install uv ffmpeg-free pipewire-utils
```

Transcription needs an NVIDIA GPU with 8 GB or more and its driver. Without one, Echo still
records, imports, plays and edits.

```sh
git clone <this repository> ~/apps/echo
cd ~/apps/echo
./install.sh --with-transcription     # or plain ./install.sh for recording only
```

The installer touches only the clone and your home directory. uv downloads its own Python,
and every package is installed from the hash-locked `uv.lock`, wheels only, so no third-party
build script runs. Nothing is installed into the system Python and nothing needs root.

Echo then appears in the application menu. From a terminal, run `echo-app`.

### The transcription model

The model is free but gated on Hugging Face. Accept the terms on both model pages with your
account, then create a read token at <https://huggingface.co/settings/tokens>. The welcome
screen asks for the token and downloads the model (about 4.3 GB) with a progress bar. The same
screen is under Help → Transcription model. From a terminal instead:

```sh
hf auth login                 # or put the token in ~/.cache/huggingface/token
echo-app models download
```

Model revisions are pinned in `src/echo_app/models.py`; only data files are downloaded, never
code from the model repositories.

## Using Echo

- **Record.** Pick the input at the top left and check the meter. Press Record (Ctrl+R). Pause
  and resume with Ctrl+Shift+R. Press Stop to save. Choosing "Computer audio: …" records what
  the computer plays, for example a call.
- **Import.** Drop audio files or folders anywhere on the window, use File → Import (Ctrl+O), or
  open a file with Echo from the file manager. WhatsApp voice notes (`.opus`, `.ogg`, `.m4a`,
  `.amr`) are recognized and dated from their file names. Duplicates are skipped.
- **Transcribe.** New recordings and imports are transcribed automatically (Settings can turn
  that off). Progress and time left show in the list. Transcription runs in the background
  while you keep recording or editing.
- **Read and edit.** Click a recording to see its transcript on the right. Edits save
  automatically. Copy (Ctrl+Shift+C), find (Ctrl+F) and export to `.txt` or `.md` (Ctrl+E).
  While playing, the current passage is highlighted; Ctrl+click a passage to jump there.
- **Crop.** Drag the edges of the waveform, or press `[` and `]` at the playhead. Edges snap to
  pauses unless you hold Shift; Ctrl+arrows nudge them. Crop never changes the original file.
  Transcribe again to transcribe only the cropped part. Export audio writes the cropped span
  as FLAC.
- **Search.** The search box matches titles and transcript text, ignoring accents.
- **Close the window while recording** and the recording continues; a tray icon shows it and
  can stop it. Opening Echo again shows the recording in progress.

All shortcuts are under Help → Keyboard shortcuts (F1).

## Command line

The window is the main way to use Echo, but every core action also works from a terminal:

```text
echo-app                          open the window (files given are imported)
echo-app record [--wait] [--source NODE] [--title T]
echo-app pause | resume | stop | status
echo-app sources                  list inputs (* marks the default)
echo-app import PATH...           import files or folders
echo-app transcribe ID... | --all [--wait] [--no-adapter]
echo-app cancel ID
echo-app list [QUERY]             list or search recordings
echo-app models download | status
echo-app recover                  repair recordings interrupted by a crash
echo-app finalize ID              retry saving a recording whose raw audio was kept
echo-app rescan                   rebuild the search index from the folders
echo-app doctor                   check the setup
```

## Update

```sh
cd ~/apps/echo && git pull && ./install.sh
```

The installer remembers whether transcription was installed.

## Uninstall

```sh
./uninstall.sh            # removes the launcher, menu entry and environment; keeps recordings
./uninstall.sh --purge    # also deletes recordings, settings and logs (asks first)
```

## Where things live

| What | Where |
|---|---|
| Recordings and transcripts | `~/.local/share/echo/recordings/` (one folder per recording) |
| Settings | `~/.config/echo/settings.toml` |
| Logs | `~/.local/state/echo/` |
| Waveform cache | `~/.cache/echo/` |
| Models | `~/.cache/huggingface/hub/` |

A recording folder holds `audio.flac` (or the imported file, unchanged), `meta.json`,
`transcript.json` (model output with passage times) and `transcript.edited.txt` once you edit.
Deleted recordings go to the desktop trash.

## Troubleshooting

Start with Help → Check setup, or `echo-app doctor`. It checks PipeWire, ffmpeg and its decoders,
the Python environment, the lockfile, disk space, the GPU, the Hugging Face login and the model
files, and says how to fix whatever fails.

- **The level meter does not move.** Pick another input; "(system default input)" in the tooltip
  marks the system default. The meter runs only while the Echo window is focused, so the
  microphone indicator is not on all the time.
- **Old voice notes (`.amr`) do not import.** Fedora's `ffmpeg-free` lacks the AMR decoder.
  Install `ffmpeg` from RPM Fusion.
- **"Not enough GPU memory".** The model needs about 5 GB free. Close other programs that use the
  GPU and try again. The transcriber frees the GPU five minutes after its last job (configurable).
- **A recording shows "Needs attention".** Its raw audio is safe in the recording's `takes/`
  folder. Try saving again from the transcript panel or with `echo-app finalize ID`.

Logs are in `~/.local/state/echo/` (`gui.log`, `recorder.log`, `worker.log`, `cli.log`).

## Development

```sh
uv sync --locked --extra worker     # full environment including dev tools
uv run --no-sync pytest             # fast suite, no GPU or microphone needed
ECHO_PIPEWIRE_TESTS=1 uv run --no-sync pytest tests/test_pipewire_integration.py   # records the default input
ECHO_MODEL_TESTS=1 uv run --no-sync pytest tests/test_model_smoke.py               # needs the GPU and models
```

Changes are planned with [OpenSpec](https://github.com/Fission-AI/OpenSpec): specs in
`openspec/specs/`, archived changes in `openspec/changes/archive/`. `PLAN.md` holds the
architecture, the decisions made while building, and the quality bar.

Updating dependencies is deliberate: move `exclude-newer` in `pyproject.toml` forward (keeping
two weeks of margin), run `uv lock --upgrade`, review the diff, run the tests.

## Credits

Speech recognition by Cohere Transcribe (Apache-2.0) with the Surus Spanish adapter
(Apache-2.0). Speech detection by Silero VAD (MIT).
