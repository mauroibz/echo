<p align="center">
  <img src="data/echo-app.svg" width="112" height="112" alt="Echo logo: foam waves and a coral dot on a deep teal tile">
</p>

<h1 align="center">Echo</h1>

<p align="center">
  Record long talks, meetings and calls, and get Spanish transcripts made on your own computer.
</p>

<p align="center">
  Spanish transcription powered by <a href="https://huggingface.co/surus-ai/cohere-transcribe-spanish-MegaASR"><b>SURUS</b></a>
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="Echo with a recording selected: the recorder and library on the deep teal sidebar, the waveform and transcript on the right" width="900">
</p>

Echo is a desktop app for Linux made for long, unscripted speech: thinking out loud,
interviews, meetings, calls, hours of voice notes. It records, transcribes and tells the
speakers apart on your computer, on an NVIDIA or AMD graphics card or on the processor.
Nothing is uploaded: after a one-time model download it works offline.

Its Spanish transcription uses **SURUS's MegaASR adapter**, a Spanish fine-tune of Cohere
Transcribe made by [SURUS](https://huggingface.co/surus-ai).

## What it does

| | |
|---|---|
| **Records without losing audio** | Saved to disk every two seconds by a background process; a crash or a power cut loses nothing. |
| **Records calls** | Your microphone and the call (Meet, Teams, Zoom) as two tracks, so it knows which side said what. |
| **Transcribes long recordings** | Passages and paragraphs with times, punctuation and accents. An hour in about a minute on a recent graphics card. |
| **Tells who said what** | Speaker labels, names it learns, interruptions as their own paragraphs, and fixes it learns from. |
| **Imports anything** | Audio, video (only its sound) and WhatsApp voice notes, dated and without duplicates. Watched folders too. |
| **Edits with the audio** | Edit the text while hearing each passage; unsure passages are marked for checking. |
| **Finds things** | Search every transcript, by tag (`#client:acme`) or by speaker (`@ana precio`). People have profiles. |
| **Exports** | Text, Markdown, SRT, VTT, JSON, or a whole Obsidian vault kept up to date. |
| **Works from scripts** | `echo-app transcribe meeting.mp4 --format md`, for scripts and AI agents. |

Everything Echo does, with its shortcuts, is in the **[user guide](docs/guide.md)**.

## Install

You need Linux with PipeWire (the default on current Fedora, Ubuntu, Debian and Arch), `ffmpeg`
and [`uv`](https://docs.astral.sh/uv/):

```sh
sudo dnf install uv ffmpeg-free pipewire-utils                 # Fedora
sudo apt install ffmpeg pipewire-bin && curl -LsSf https://astral.sh/uv/install.sh | sh   # Ubuntu, Debian
sudo pacman -S uv ffmpeg pipewire                              # Arch
```

Then:

```sh
git clone https://github.com/mauroibz/echo.git ~/apps/echo
cd ~/apps/echo
./install.sh --with-transcription     # or ./install.sh to record only
```

Echo appears in your application menu; from a terminal, run `echo-app`. The installer needs no
root and touches only the cloned folder and your home. Every package comes hash-locked from
`uv.lock` as a prebuilt wheel, and nothing goes into the system Python.

**For transcription** you need one of: an NVIDIA card from the RTX 30 series on with 6 GB or
more (an hour in about a minute), or any 64-bit processor with 8 GB of RAM (an hour in five to
ten minutes on a recent desktop). AMD cards with ROCm are supported by the installer but not yet
tested. The installer picks the right build and says which; `--with-transcription=cuda`, `=rocm`
or `=cpu` chooses. Count on about 5 GB of disk for the model and 1 to 5 GB for the libraries.

### The transcription model

The models are free, but you accept their terms on Hugging Face first:

1. Sign in to [Hugging Face](https://huggingface.co) and accept the terms of
   [Cohere Transcribe](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026) and of
   [SURUS's Spanish adapter](https://huggingface.co/surus-ai/cohere-transcribe-spanish-MegaASR).
2. Create a read token at <https://huggingface.co/settings/tokens>.
3. Open Echo: the welcome screen asks for the token and downloads the model (about 4.3 GB). It is
   also under Help → Transcription model. From a terminal: `hf auth login`, then
   `echo-app models download`.

Model versions are pinned, and only weights and configuration are downloaded, never code.

### Update and uninstall

Releases are tagged and listed in [CHANGELOG.md](CHANGELOG.md).

```sh
cd ~/apps/echo
git fetch --tags && git checkout "$(git describe --tags --abbrev=0 origin/main)"
./install.sh              # remembers whether transcription was installed

./uninstall.sh            # removes the launcher, menu entry and environment; keeps recordings
./uninstall.sh --purge    # also deletes recordings, settings and logs (asks first)
```

Something not working? Help → Check setup (or `echo-app doctor`) names what is wrong and the
command that fixes it; more in [Troubleshooting](docs/guide.md#troubleshooting).

## Development

```sh
uv sync --locked --extra cuda       # full environment including test tools (or cpu, rocm)
uv run --no-sync pytest             # fast suite, no GPU or microphone needed
ECHO_PIPEWIRE_TESTS=1 uv run --no-sync pytest tests/test_pipewire_integration.py   # records the default input
ECHO_MODEL_TESTS=1 uv run --no-sync pytest tests/test_model_smoke.py               # needs the GPU and model
```

[docs/design.md](docs/design.md) explains the architecture and the reasons behind it. Behavior
is specified with [OpenSpec](https://github.com/Fission-AI/OpenSpec) in `openspec/specs/`, and
each past change is in `openspec/changes/archive/`. Updating dependencies is deliberate: move
`exclude-newer` in `pyproject.toml` forward (keeping two weeks of margin), run
`uv lock --upgrade`, review the diff and run the tests.

## Credits

**Spanish speech recognition by [SURUS](https://huggingface.co/surus-ai).** Echo transcribes
Spanish with SURUS's
[MegaASR adapter](https://huggingface.co/surus-ai/cohere-transcribe-spanish-MegaASR)
(Apache-2.0) on top of [Cohere Transcribe](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026)
(Apache-2.0).

Also: speech detection by Silero VAD (MIT); speaker models from WeSpeaker (Apache-2.0) and
pyannote (MIT); icons from [Lucide](https://lucide.dev) (ISC); common Spanish words from
[FrequencyWords](https://github.com/hermitdave/FrequencyWords) (CC BY-SA 4.0); type set in
[Manrope](https://github.com/sharanda/manrope) (SIL Open Font License), with the static weights in
`src/echo_app/ui/assets/fonts/` cut from the variable font. The models are downloaded separately
under their own terms; license texts sit next to the bundled files.

Echo is released under the [MIT License](LICENSE).
