# Echo

Record long-form audio and transcribe Spanish speech locally, on your own GPU.

Echo is a desktop app for Linux (PipeWire). It records from any input, imports audio from
other sources such as WhatsApp voice notes, and transcribes Spanish speech with
[Cohere Transcribe](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026) plus the
[Surus Spanish adapter](https://huggingface.co/surus-ai/cohere-transcribe-spanish-MegaASR).
Nothing leaves your machine after the one-time model download.

## Install

Requirements: Linux with PipeWire, `ffmpeg`, and [`uv`](https://docs.astral.sh/uv/)
(`sudo dnf install uv ffmpeg-free pipewire-utils` on Fedora). Transcription needs an NVIDIA
GPU with 8 GB or more and its driver.

```sh
git clone <this repo> ~/apps/echo
cd ~/apps/echo
./install.sh --with-transcription     # or plain ./install.sh for recording only
```

The installer touches only the clone and your home directory. uv downloads its own Python,
and every package is installed from the hash-locked `uv.lock`, wheels only. Nothing is
installed into the system Python and nothing needs root.

Echo then appears in the application menu. From a terminal, run `echo-app`.

The transcription models are gated on Hugging Face. Accept the terms on both model pages,
log in once with `hf auth login` (or put a token in `~/.cache/huggingface/token`), then
download them from the app's welcome screen or with:

```sh
echo-app models download      # about 4.3 GB, pinned revisions
```

Check the setup at any time:

```sh
echo-app doctor
```

## Update

```sh
cd ~/apps/echo && git pull && ./install.sh
```

The installer remembers whether transcription was installed.

## Uninstall

```sh
./uninstall.sh            # removes launcher, menu entry and the environment; keeps recordings
./uninstall.sh --purge    # also deletes recordings, settings and logs (asks first)
```

## Where things live

| What | Where |
|---|---|
| Recordings and transcripts | `~/.local/share/echo/recordings/` (one folder per recording) |
| Settings | `~/.config/echo/settings.toml` |
| Logs | `~/.local/state/echo/` |
| Models | `~/.cache/huggingface/hub/` |

Each recording folder is self-contained: the audio, `meta.json`, the model transcript, and
your edited text. The library index can be rebuilt from these folders at any time with
`echo-app rescan`.

## Development

```sh
uv sync --locked --extra worker     # full environment including dev tools
uv run --no-sync pytest
```

Changes are planned with [OpenSpec](https://github.com/Fission-AI/OpenSpec) under
`openspec/`. `PLAN.md` holds the architecture and the quality bar.

Updating dependencies is deliberate: move `exclude-newer` in `pyproject.toml` forward
(keeping two weeks of margin), run `uv lock --upgrade`, review the diff, run the tests.
