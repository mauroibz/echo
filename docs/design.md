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
through signals and two small JSON files; it finds running supervisors by their command line in
`/proc`. Every action in the window is also a CLI command (`echo-app record`, `transcribe`,
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
   and twice a second. Pause and resume are SIGUSR1 and SIGUSR2; each resume starts a new take.
   Stop is SIGTERM.
3. If capture dies, the supervisor restarts it into a new take with backoff and records the gap.
   After repeated failures on the chosen input it falls back to the default input and says so.
   It warns when the take stops growing and refuses to start with less than 1 GB free.
4. On stop, the takes are encoded to FLAC. The FLAC is kept only if it decodes to exactly the
   captured PCM (sha256 of the decoded samples); then the takes are deleted. Any failure leaves
   the takes in place and the recording marked "needs attention".
5. On startup the window and `echo-app recover` look for interrupted recordings: a live
   supervisor is reattached, a live `pw-record` without its supervisor is adopted, and if
   everything is dead the takes are finalized.

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

The stock feature extractor needs librosa; Echo subclasses it to use transformers' own Slaney
mel filterbank, which matches librosa to within 4e-9 and keeps librosa, numba, scipy and
scikit-learn out of the environment.

The queue is the marker files in each recording folder. One worker per user holds a lock in the
runtime directory; if the user switches data folders, the worker hands over through a
`worker.wanted` file, because the GPU holds one model at a time. The worker exits after a
configurable idle time to free GPU memory.

Measured on an RTX 3080: 20 minutes of speech in 18 seconds and 32 minutes in 23 seconds,
including model load.

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

Two install profiles: the default has PySide6 and numpy and records, imports, plays and edits;
`--with-transcription` adds torch, transformers, peft and silero-vad. CUDA libraries come inside
the torch wheels, so the host needs only the NVIDIA driver.

`exclude-newer` in `pyproject.toml` keeps resolution at least two weeks behind the newest
releases. Updating is deliberate: move the date, `uv lock --upgrade`, review the diff, run the
tests.

Not chosen: running the worker in a Podman container (needs a root-installed GPU toolkit per
machine), serving the model with vLLM (unverified LoRA support, larger dependency tree),
Flatpak (CUDA inside Flatpak is painful and the recorder needs raw PipeWire), and distro Python
packages (Fedora's torch is CPU-only).

## Next

- **Knowledge base.** A glossary of people and terms. In-model biasing is ready: the worker
  accepts a per-job `context`, and the glossary only has to produce the sentence. Post-hoc
  correction for what biasing misses would be a separate, logged and reversible layer on top of
  the immutable model output.
- **Speaker recognition.** The model does not do it. Speaker embeddings per speech segment,
  clustered and labeled, would fit on the existing segment boundaries; known speakers could live
  in the same glossary.
