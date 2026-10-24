<p align="center">
  <img src="data/echo-app.svg" width="112" height="112" alt="Echo logo: foam waves and a coral dot on a deep teal tile">
</p>

<h1 align="center">Echo</h1>

<p align="center">
  Record long talks and voice notes, and get Spanish transcripts made on your own computer.
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="Echo with a recording selected: the recorder and library on the deep teal sidebar, the waveform and transcript on the right" width="900">
</p>

Echo is a desktop app for Linux. It records from any microphone, or from whatever the computer
is playing, imports audio from anywhere (WhatsApp voice notes included), and transcribes
Spanish speech on your own computer, on an NVIDIA or AMD graphics card or on the processor.
Nothing is uploaded: after a one-time model download it works offline.

It is made for long, unscripted speech: thinking out loud, interviews, meetings, hours of
voice notes.

## What it does

- **Records without losing audio.** Recording runs in its own background process and is saved
  to disk every two seconds. Closing the window, a crash or a power cut loses nothing that
  reached the disk, and the next start recovers the recording by itself. Finished recordings
  are lossless FLAC, kept only after Echo checks they decode to exactly what was captured.
- **Transcribes long recordings well.** Speech is split at natural pauses into passages and
  paragraphs with timing, punctuation and accents. An RTX 3080 transcribes an hour of audio in
  under a minute; a 6-core desktop processor in about five.
- **Imports anything.** Drag files or folders onto the window. WhatsApp voice notes (`.opus`,
  `.m4a`, `.amr`) are recognized and dated from their names, and duplicates are skipped.
- **Lets you work with the text.** Click a recording to read its transcript, edit it (edits
  save automatically and are never overwritten), search every transcript at once, copy or
  export to `.txt` or `.md`, and Ctrl+click a passage to hear it.
- **Plays and crops.** A waveform with speed control and non-destructive crop that snaps to
  pauses.
- **Keeps your files plain.** Each recording is a folder with its audio, a `meta.json` and its
  transcripts.

Transcription uses [Cohere Transcribe](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026)
with the [Surus Spanish adapter](https://huggingface.co/surus-ai/cohere-transcribe-spanish-MegaASR).

## Requirements

- Linux with PipeWire (the default on current Fedora, Ubuntu, Debian and Arch desktops)
- `ffmpeg`
- [`uv`](https://docs.astral.sh/uv/), which installs Echo's own Python
- For transcription, one of:
  - an NVIDIA GPU with 8 GB of memory or more and its driver: an hour of audio in under a
    minute (RTX 3080);
  - any 64-bit processor with 8 GB of RAM: an hour of audio in about five minutes on a 6-core
    Ryzen 5 7600X, longer on smaller machines;
  - an AMD GPU on Linux with ROCm (supported by the installer but not yet tested on real
    hardware; please report how it goes).

  Plus about 5 GB of disk for the model, and 1 GB (processor) to 5 GB (GPU) for the libraries.
  Without transcription Echo still records, imports, plays and edits.

Install the system packages:

```sh
# Fedora
sudo dnf install uv ffmpeg-free pipewire-utils

# Ubuntu / Debian
sudo apt install ffmpeg pipewire-bin
curl -LsSf https://astral.sh/uv/install.sh | sh

# Arch
sudo pacman -S uv ffmpeg pipewire
```

## Install

```sh
git clone https://github.com/mauroibz/echo.git ~/apps/echo
cd ~/apps/echo
./install.sh --with-transcription     # or ./install.sh for recording only
```

`--with-transcription` picks the build for your hardware (NVIDIA, AMD or the processor) and
says which. To choose yourself: `--with-transcription=cuda`, `=rocm` or `=cpu`. Echo tells you
how long transcription takes on your computer once it has done a first job; Help → Check
setup shows it.

Echo then appears in your application menu. From a terminal, run `echo-app`.

The installer touches only the folder you cloned and your home directory, and needs no root.
Every package comes from the hash-locked `uv.lock` as a prebuilt wheel, so no third-party build
script runs, and nothing is installed into the system Python.

### Get the transcription model

The model is free, but you have to accept its terms on Hugging Face first:

1. Sign in to [Hugging Face](https://huggingface.co) and accept the terms on both
   [Cohere Transcribe](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026) and the
   [Surus adapter](https://huggingface.co/surus-ai/cohere-transcribe-spanish-MegaASR).
2. Create a read token at <https://huggingface.co/settings/tokens>.
3. Open Echo. The welcome screen asks for the token and downloads the model (about 4.3 GB).
   The same screen is under Help → Transcription model.

From a terminal instead:

```sh
hf auth login                 # or put the token in ~/.cache/huggingface/token
echo-app models download
```

Model versions are pinned, and only weights and configuration are downloaded, never code.

## Using Echo

- **Record.** Pick the input at the top left and speak; the meter and the waves should move.
  Press Record (Ctrl+R), pause with Ctrl+Shift+R, press Stop to save. "Computer audio: …"
  records what the computer plays, for example a call.
- **Import.** Drop audio files or folders on the window, use File → Import (Ctrl+O), or open a
  file with Echo from your file manager.
- **Transcribe.** New recordings and imports are transcribed automatically; progress and time
  left show in the list. You can keep recording and editing meanwhile.
- **Read and edit.** Click a recording. Copy with Ctrl+Shift+C, find with Ctrl+F, export with
  Ctrl+E. While playing, the current passage is highlighted.
- **Crop.** Drag the edges of the waveform, or press `[` and `]` at the playhead. Hold Shift to
  turn off snapping. Transcribe again to transcribe only the cropped part.
- **Search.** The search box matches titles and transcript text, ignoring accents.
- **Close the window while recording** and the recording continues, with a tray icon to stop
  it.
- **Appearance.** Light by default; Settings → Appearance switches to dark or follows the
  system.

All shortcuts are under Help → Keyboard shortcuts (F1).

## Command line

Every core action also works from a terminal:

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

## Update and uninstall

Releases are tagged and listed in [CHANGELOG.md](CHANGELOG.md). To update to the latest one:

```sh
cd ~/apps/echo
git fetch --tags && git checkout "$(git describe --tags --abbrev=0 origin/main)"
./install.sh              # remembers whether transcription was installed

./uninstall.sh            # removes the launcher, menu entry and environment; keeps recordings
./uninstall.sh --purge    # also deletes recordings, settings and logs (asks first)
```

## Where things live

| What | Where |
|---|---|
| Recordings and transcripts | `~/.local/share/echo/recordings/`, one folder per recording |
| Settings | `~/.config/echo/settings.toml` |
| Logs | `~/.local/state/echo/` |
| Waveform cache | `~/.cache/echo/` |
| Models | `~/.cache/huggingface/hub/` |

A recording folder holds `audio.flac` (or the imported file, unchanged), `meta.json`,
`transcript.json` (model output with passage times) and `transcript.edited.txt` once you edit.
Deleted recordings go to the desktop trash.

## Troubleshooting

Start with Help → Check setup, or `echo-app doctor`. It checks PipeWire and whether it owns
the audio devices, ffmpeg and its decoders, the libraries the window needs, the Python
environment, disk space, the GPU, the Hugging Face login and the model files, and gives the
command for your distribution that fixes whatever fails (including Ubuntu 22.04, where
PulseAudio still owns audio, and X11 sessions missing `libxcb-cursor0`).

- **The meter does not move.** Pick another input. If Echo says no sound is arriving, check the
  cable, the mute switch and the input gain, in the system sound settings or on your audio
  interface.
- **Old voice notes (`.amr`) do not import.** Fedora's `ffmpeg-free` lacks the AMR decoder;
  install `ffmpeg` from RPM Fusion. Doctor lists the missing decoders.
- **"Not enough GPU memory".** The model needs about 5 GB free. Close other programs using the
  GPU. Echo frees the GPU five minutes after its last transcription (configurable in Settings).
- **A recording shows "Needs attention".** Its raw audio is safe in the recording's `takes/`
  folder. Use "Try saving again" in the transcript panel, or `echo-app finalize ID`.

Logs are in `~/.local/state/echo/`.

## Development

```sh
uv sync --locked --extra cuda       # full environment including test tools (or cpu, rocm)
uv run --no-sync pytest             # fast suite, no GPU or microphone needed
ECHO_PIPEWIRE_TESTS=1 uv run --no-sync pytest tests/test_pipewire_integration.py   # records the default input
ECHO_MODEL_TESTS=1 uv run --no-sync pytest tests/test_model_smoke.py               # needs the GPU and model
```

[docs/design.md](docs/design.md) explains the architecture and the reasons behind it. Behavior
is specified with [OpenSpec](https://github.com/Fission-AI/OpenSpec) in `openspec/specs/`, and
each past change is in `openspec/changes/archive/`.

Updating dependencies is deliberate: move `exclude-newer` in `pyproject.toml` forward (keeping
two weeks of margin), run `uv lock --upgrade`, review the diff and run the tests.

## License and credits

Echo is released under the [MIT License](LICENSE).

Speech recognition by Cohere Transcribe (Apache-2.0) with the Surus Spanish adapter
(Apache-2.0); speech detection by Silero VAD (MIT). The models are downloaded separately under
their own terms. Icons from [Lucide](https://lucide.dev) (ISC). Interface type set in
[Manrope](https://github.com/sharanda/manrope) (SIL Open Font License); the static weights in
`src/echo_app/ui/assets/fonts/` are cut from the variable font. License texts sit next to those
files.
