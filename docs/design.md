# Echo design

How Echo is built and why. The README covers installing and using it; `openspec/specs/` holds
the behavior each part must keep, and `openspec/changes/archive/` the reasoning behind each
change.

## Principles

- **No lost audio.** Audio never passes through the UI process. Whatever bytes reached the disk
  are recoverable, whichever process dies.
- **Plain files are the truth.** Every recording is a folder. The SQLite index is a cache that
  can be rebuilt from the folders at any time.
- **Lean.** A few features done completely, defaults that work, and a short dependency list
  whose every entry has a reason.
- **No root, no surprises.** The install touches only the clone and the user's home, and gets
  the same hash-locked packages on every machine.

## Processes

| Process | Started by | Job |
|---|---|---|
| Window (`echo-app`) | the user | Library, controls, player, editor. Never imports torch. |
| Recorder supervisor (`echo-app _recorder ID`) | the window or the CLI, detached | Runs `pw-record` for one recording and finalizes it. |
| `pw-record` | the supervisor | Writes raw PCM to disk. |
| Transcription worker (`echo-app _worker`) | on demand, one per user | Loads the model on the GPU, works through queued recordings, exits when idle. |

Each of the first three can die without losing audio. The window talks to the supervisor
through files only: commands (pause, resume, stop) are one-line files in `takes/commands/`, read
on every 0.1 s tick, and the supervisor answers in `status.json`, a heartbeat written twice a
second with the random token it also put in `session.json`. A supervisor is alive while its
heartbeat is under 3 seconds old, carries the session's token and its process exists; nothing
reads `/proc`. A heartbeat that stops is given 10 seconds before recovery treats the supervisor
as dead, and recovery never touches a recording whose supervisor process still holds the
recording lock. The previous version's signals are still accepted, and a recording it started
(no token) is still stopped with a signal. All audio device access goes through
`audio/backend.py`; PipeWire is the only backend so far, and the tests use a command backend
that runs `tests/fake_capture.py` in place of `pw-record`. Locks are `locks.py`: `flock` on
POSIX, `msvcrt.locking` on Windows. Every action in the window is also a CLI command (`echo-app record`, `transcribe`,
`import` and so on), which is how the core is tested without a display.

## Storage

```
~/.local/share/echo/
  library.sqlite                  index with FTS5 search (rebuildable cache)
  recordings/<id>/                id = creation time + 4 hex digits
    meta.json                     title, source, created, duration, sha256, crop, gaps
    takes/take-NNN.raw            raw PCM, only while recording or awaiting finalize
    session.json, status.json     supervisor state and heartbeat, only while recording
    audio.<ext>                   recorded FLAC, or the imported file byte for byte
    transcript.json               model output with passage times (replaced per run)
    transcript.corrected.json     the model output with dictionary corrections, each logged
    transcript.edited.txt         the user's text; the transcriber never writes it
    transcribe.requested          job marker with options
    transcribe.progress.json      written by the worker while it runs
    transcript.partial.json       finished passages, for resuming after a crash
    transcribe.error              last failure
```

Writes are atomic (temporary file, fsync, rename, fsync of the folder). Crop is stored as in
and out points in `meta.json`; the original audio is never changed. Deleting moves the folder
to the desktop trash.

## Recording

1. `echo-app record` takes a per-data-folder lock (one recording at a time) and starts a
   detached supervisor, which runs `pw-record --raw` into `takes/take-001.raw`.
2. The supervisor fsyncs the take every 2 seconds and writes `status.json` on each state change
   and twice a second, also while it finalizes. Pause, resume and stop are command files; each
   resume starts a new take.
3. If capture dies, the supervisor restarts it into a new take with backoff and records the gap.
   After repeated failures on the chosen input it falls back to the default input and says so.
   It warns when the take stops growing and refuses to start with less than 1 GB free.
4. On stop, the takes are encoded to FLAC. The FLAC is kept only if it decodes to exactly the
   captured PCM (sha256 of the decoded samples); then the takes are deleted. Any failure leaves
   the takes in place and the recording marked "needs attention".
5. On startup the window and `echo-app recover` look for interrupted recordings: a live
   supervisor is reattached, a `pw-record` still writing its take without a supervisor is
   adopted (its process exists and the take was written within 3 seconds), and if everything is
   dead the takes are finalized.

Measured PipeWire behavior this relies on: SIGINT and SIGTERM flush everything; a SIGKILL of
`pw-record` loses at most its 4 KB buffer (about 40 ms); a missing or unplugged target falls
back to the default input; `stream.capture.sink=true` captures what the computer plays.

Before recording, a low-rate `pw-record` stream drives the level meter while the window is
shown. After four seconds of exact digital silence Echo says so, because a connected
microphone with its gain up never produces it.

## Import

Files are probed with ffprobe, copied to a staging file, verified by hash and renamed into a new
recording folder unchanged. Duplicates are found by hash. WhatsApp names (`PTT-…`, `AUD-…`,
"WhatsApp Audio/Ptt … at/a las …", 12-hour and Spanish variants) give the recording its date.

## Transcription

Model: [Cohere Transcribe](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026)
(2 B parameters, about 4.2 GB in bf16) with the
[Surus Spanish LoRA adapter](https://huggingface.co/surus-ai/cohere-transcribe-spanish-MegaASR)
through PEFT. Both are pinned to commit hashes in `src/echo_app/models.py`, loaded from
safetensors only, without `trust_remote_code`, and with the Hugging Face hub offline at run
time.

1. ffmpeg decodes the audio (honoring crop) to 16 kHz mono.
2. silero-vad finds speech (threshold 0.4, 300 ms minimum silence, 100 ms padding).
3. Speech is planned into passages of at most 28 seconds, cut at the widest pause and preferring
   passages of 8 seconds or more. Paragraphs start at pauses of 2 seconds or more, after 90
   seconds of speech at the next half-second pause, and always after 150 seconds.
4. Passages are transcribed in batches of 8, halving the batch on GPU out-of-memory. Finished
   passages are saved as they complete, so a restarted job resumes where it stopped.

The model's decoder accepts text in its context slot, though the model card does not say so.
Echo puts a style sentence there ("El texto que sigue está escrito en español correcto, con
mayúsculas, tildes y signos de puntuación."). In one 102-passage test chapter it cut the
passages transcribed without punctuation from 48 to 1. Naming people and terms there also fixes
their spelling. If a passage comes back implausibly short (under 0.4 words per second), it is
retried with the style sentence only, then with no context, so context can never silently drop
speech.

### Dictionary

`~/.config/echo/glossary.toml` holds people and terms, each with a canonical spelling,
aliases and when it was last used. It is applied in two layers, both driven by the app:

- **In the model.** Every request builds a context sentence: the recording's optional line
  ("who is speaking, what about"), then "Personas: … Términos: …" with the most recently used
  entries first, cut at about 120 tokens. It is stored in `transcribe.requested`, so the worker
  needs nothing new, and recorded in the transcript. The short-output retry described above is
  the safety net against a sentence that breaks a passage.
- **After the model.** The corrector replaces recorded aliases, and multi-word names within a
  0.9 similarity ratio, in a copy (`transcript.corrected.json`), logging each replacement so
  the editor underlines it and can undo it; undone spots are kept in that file and never
  corrected again. A single common word is never replaced. It runs in the worker after each
  job and in the window whenever the dictionary changed, so a new alias reaches old
  transcripts without re-transcribing. It never runs on text the user edited.

Entries are learned, not typed. On each save of an edit, the edited words are aligned with the
model's (difflib on folded words). A replacement of one to three words is offered as a chip
under the editor when its new spelling is capitalized away from a sentence start, or when the
same replacement was made in another recording (counted in `~/.local/state/echo/
candidates.json`). Pure case or accent fixes of the 5,000 most common Spanish words are
ignored ("como" to "cómo"). Declining mutes the word. Capitalized words typed into a title are
offered the same way.

The stock feature extractor needs librosa; Echo subclasses it to use transformers' own Slaney
mel filterbank, which matches librosa to within 4e-9 and keeps librosa, numba, scipy and
scikit-learn out of the environment.

The queue is the marker files in each recording folder. One worker per user holds a lock in the
runtime directory; if the user switches data folders, the worker hands over through a
`worker.wanted` file, because the GPU holds one model at a time. The worker exits after a
configurable idle time to free GPU memory.

Measured on an RTX 3080: 20 minutes of speech in 18 seconds and 32 minutes in 23 seconds,
including model load.

### On the processor

The same model runs on the CPU with the same planning and output. The engine there uses int8
weights for the linear layers (dynamic quantization; the LoRA layers stay float), one thread
per physical core, and batches of four passages when 6 GB of memory are free. Measured on a
Ryzen 5 7600X (6 cores, AVX-512 BF16) against the GPU output on the same passages, with word
agreement in parentheses (lower case, punctuation ignored):

| Recording | GPU (RTX 3080) | float32 | bf16 | int8 | int8, batch 4 |
|---|---|---|---|---|---|
| 6.4 min, own microphone | 134× | 5.0× (99.90%) | 9.8× (100%) | 13.5× (99.90%) | 17.1× (99.90%) |
| 20.7 min, audiobook chapter | 164× | 5.4× (99.93%) | 9.8× (99.97%) | 13.9× (99.20%) | 19.1× (99.17%) |
| 62.3 min, four chapters | 176× | 5.3× (99.84%) | 9.5× (99.96%) | 13.3× (99.06%) | 16.8× (99.02%) |

Speeds are seconds of audio per second of recognition; speech detection adds about 25 s per
hour of audio on either device, and loading the model 3 s (GPU) or 9 s (CPU, quantizing). With
11 threads instead of 6, float32 was slower (4.6× against 5.4×): hyperthreads share the vector
units. So an hour of audio takes about 50 seconds on the GPU and four to five minutes on this
processor.

The rule was to keep the fastest configuration that agrees with the GPU on at least 99% of
words on all three recordings; int8 with batches of four is it. Most of its differences are
punctuation, and in several places it kept words the GPU run dropped. bf16 agrees more closely
(99.96% or better) at half the speed and needs a CPU with native bf16 (AVX-512 BF16 or AMX);
it is the choice if the remaining int8 differences turn out to matter in daily use.

### Passage times for edited text

The editor, the margin times, follow-along and the timed exports (SRT, VTT, JSON, "copy with
timestamps") all need to know which passage a piece of the shown text belongs to, also after the
user has edited it. `align.py` aligns the folded words of the model text and the shown text with
difflib; each passage starts at the first of its words that still matches, a passage whose words
were all deleted is dropped, words added after a paragraph break belong to the next passage, and
a start that would go backwards (a sentence moved elsewhere) is ignored. While the user types,
the alignment is redone 0.4 s after the last keystroke.

## Window

PySide6 (`PySide6-Essentials` only). Playback is ffmpeg piped into `pw-play`, which avoids
QtMultimedia and the several hundred megabytes of the Addons wheel. A second launch forwards
its files to the running window over a local socket. Closing the window while recording leaves a
tray icon; the recording continues.

The look ("Lagoon") lives in `src/echo_app/ui/theme.py`: color tokens for light and dark, the
palette, one stylesheet, icons tinted at paint time and the wave painter. Custom-drawn widgets
read the current tokens when they paint, so switching appearance is live. Icons (Lucide) and the
interface typeface (Manrope) are bundled so Echo looks the same on any desktop; transcripts use
the desktop's own text face.

## Packaging and dependency risk

| Thing | Where |
|---|---|
| CPython 3.14 | downloaded by uv (`python-preference = "only-managed"`); the system Python is never used |
| Packages | `<clone>/.venv`, from `uv.lock` with sha256 hashes, wheels only (`no-build = true`) |
| Echo itself | not built or installed as a package (`package = false`); `bin/echo-app` runs the source tree |
| Launcher, menu entry, icon | `~/.local/bin`, `~/.local/share/applications`, `~/.local/share/icons` |
| Models | `~/.cache/huggingface/hub` |

The default install has PySide6 and numpy and records, imports, plays and edits.
`--with-transcription` adds torch, transformers, peft and silero-vad in one of three compute
profiles, uv extras that differ only in where torch comes from: `cuda` (PyPI's torch, with the
CUDA libraries inside the wheels, so the host needs only the NVIDIA driver; about 5 GB),
`cpu` (PyTorch's CPU-only wheels; about 1 GB) and `rocm` (PyTorch's ROCm wheels, Linux only).
The extras conflict with each other and the PyTorch indexes are `explicit`, so one hash-locked
`uv.lock` covers all three and nothing else is ever resolved from those indexes. The installer
picks the profile from the hardware (`nvidia-smi` or `/proc/driver/nvidia`, then `/dev/kfd`);
the profile in use is read back from torch's version tag (`+cpu`, `+rocm7.2`). Each finished
job records its speed in `~/.local/state/echo/speed.json`, from which the window, the model
dialog and doctor say how long transcription takes on this computer.

A GitHub Actions workflow (`.github/workflows/test.yml`) runs the fast suite on Ubuntu and in a
Fedora container on every push and checks that the transcription profile still resolves from the
lockfile. `install.sh` installs the pinned Python with `uv python install` before syncing, because
distribution builds of uv (Fedora's) turn automatic Python downloads off. Releases are tagged
`vX.Y.Z` and listed in `CHANGELOG.md`.

`exclude-newer` in `pyproject.toml` keeps resolution at least two weeks behind the newest
releases. Updating is deliberate: move the date, `uv lock --upgrade`, review the diff, run the
tests.

Not chosen: running the worker in a Podman container (needs a root-installed GPU toolkit per
machine), serving the model with vLLM (unverified LoRA support, larger dependency tree),
Flatpak (CUDA inside Flatpak is painful and the recorder needs raw PipeWire), and distro Python
packages (Fedora's torch is CPU-only).

## Next

- **A personal adapter.** A LoRA trained on the user's own corrected transcripts (the model
  and edited texts Echo keeps side by side), for systematic errors prompting cannot fix. Not
  before the dictionary has been in daily use. See `docs/roadmap.md`.
- **Speaker recognition.** The model does not do it. Speaker embeddings per speech segment,
  clustered and labeled, would fit on the existing segment boundaries; known speakers could live
  in the same glossary.
