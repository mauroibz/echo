# echo — local audio recorder + Spanish transcription

Plan written 2026-10-23. Target machine: Fedora 44 KDE, PipeWire 1.6.9, RTX 3080 10 GB,
30 GB RAM, Python 3.14 + uv, ffmpeg, GStreamer, pw-record all present.

## 0. Status (as built, 2026-10-23)

Milestones M0 to M5 are implemented, tested and archived as OpenSpec changes under
`openspec/changes/archive/`; the resulting capability specs live in `openspec/specs/`.
Where the build departed from the original plan, the table below says what changed and why.
Sections 1 to 10 have been corrected to match.

| Planned | Built | Why |
|---|---|---|
| CLI named `echo` | `echo-app` | A command named `echo` is shadowed by the shell builtin. |
| uv builds the project (`--no-build` for deps) | No build at all: `package = false`, `bin/echo-app` runs the source tree | Keeps "wheels only" absolute; not even our own package is built. |
| Playback through QtMultimedia (`PySide6-Addons`) | ffmpeg piped into `pw-play` | QtMultimedia lives in the Addons wheel (hundreds of MB). ffmpeg and PipeWire are already required and decode every importable format. |
| UI process watches capture | Detached recorder supervisor per recording (`echo-app _recorder`) | The window, the supervisor and `pw-record` can each die without losing audio. |
| Job queue in SQLite | Marker files in each recording folder | The queue survives index loss and lives with the data. SQLite is only a rebuildable cache with full-text search. |
| One worker per data folder | One worker per user, with a handover between folders | The GPU holds one 5 GB model; two workers ran out of memory in testing. |
| Model card says no prompting | The decoder has a context slot, and it works | A style sentence there fixes unpunctuated passages (48 of 102 down to 1 in one chapter); known terms there fix spellings ("Zurus" to "Surus"). This is the hook for the knowledge base. |
| librosa (pulled by the stock feature extractor) | Subclass using transformers' own Slaney mel filterbank | Identical to 4e-9; avoids librosa, numba, scipy and scikit-learn. |

Measured on the target machine: 20 min of Spanish audio transcribed in 18 s and 32 min in 23 s
(about 70x real time, including model load); window interactive in 0.2 s with 500 recordings;
kill-and-recover against real PipeWire loses nothing (duration matches wall clock within 1 s).

## 1. Decisions

| Area | Choice | Why |
|---|---|---|
| Language | Python 3.14, **uv-managed interpreter**, hash-locked deps | The ASR model is PyTorch/transformers; one language for everything. All deps (torch 2.14, transformers 5.20, peft, PySide6 6.12, silero-vad) resolve on 3.14 today. uv downloads its own CPython; the system Python is never used or written to. See §9. |
| Install | `git clone` + `./install.sh` (runs `uv sync --locked --no-build`), everything under the clone and `~/.local` | One bootstrap dependency (the `uv` binary). No root, no system site-packages, reproducible on a new machine from the lockfile. See §9. |
| UI | PySide6 (Qt 6) desktop app: `PySide6-Essentials` only | Native on KDE, built-in drag/drop, list views, text editing, no browser or JS build step. Qt ships inside the wheel. Playback is ffmpeg piped into `pw-play` (see §0). |
| Capture | `pw-record --raw` subprocess, detached from the UI | Audio never flows through Python; the UI can crash or freeze without touching the recording. PipeWire-native, so every source Qt/pactl sees is selectable. |
| On-disk recording format | Raw PCM (`s16le`, 48 kHz, mono or stereo) + JSON sidecar while recording; FLAC after stop | Raw PCM has no header to corrupt: whatever bytes reached disk are playable. FLAC is lossless and ~50 % smaller. |
| Import/decode | `ffmpeg` subprocess | Handles WhatsApp `.opus` (Ogg), `.m4a/.aac`, `.amr`, `.mp3`, `.wav`, `.flac`, `.ogg`, `.webm`, `.wma`. |
| Library index | SQLite (`library.sqlite`) with FTS5 search | A cache: the folder tree is the source of truth and the index is rebuildable by rescanning. |
| ASR | `CohereLabs/cohere-transcribe-03-2026` (2.08 B, bf16 ≈ 4.2 GB) + LoRA `surus-ai/cohere-transcribe-spanish-MegaASR` via PEFT. **Pinned to commit hashes, safetensors only, no `trust_remote_code`** | Fits the 3080 with room for batching. Adapter is togglable per job. The model class is native in transformers ≥ 5.4, so no code is executed from the HF repo. |
| Segmentation | silero-vad → speech segments → windows ≤ 30 s | The model has no timestamps and transcribes non-speech noises (model card recommends a VAD). VAD gives us timestamps, resumability, batching, and matches the adapter's ≤ 30 s training clips. |
| Transcription worker | Separate process (`echo-app _worker`) polling marker files in recording folders | UI never imports torch. Exits when idle to free VRAM. One per user. |

Things the model does **not** do: timestamps, diarization, language auto-detect. The model
cards do not mention prompting, but the decoder's context slot works (see §0 and §7). Both
repos are **gated**: you must accept the terms on Hugging Face for both and log in once (or
paste a token in the app's welcome screen).

## 2. Storage layout

```
~/.local/share/echo/                 (XDG data dir; configurable)
  library.sqlite                     index + job queue (rebuildable)
  recordings/
    2026-10-23T20-31-05_a3f9/         one folder per item, human-readable id
      meta.json                      title, source, created, duration, sha256, crop in/out, tags
      takes/                         only while recording
        take-001.raw                 raw PCM, appended continuously
        take-001.json                rate, channels, format, start_ts, pid
        take-002.raw ...             one take per pause/resume
      original.flac                  finalized recording (or imported file kept byte-identical,
                                     e.g. PTT-20261023-WA0003.opus)
      normalized.wav                 16 kHz mono cache for ASR; regenerable
      transcript.json                segments: {start, end, text, model, adapter, created}
      transcript.edited.txt          user edits; never overwritten by re-transcription
      corrections.json               (future) applied knowledge-base replacements with provenance
```

Rules: originals are never modified or deleted by the app. Crop is non-destructive (stored as
in/out points in `meta.json`; player and transcriber honor them; "Export cropped" writes a new file).
Imports are copied, not moved.

## 3. Recording engine (the "no lost audio" part)

1. **Start**: create take folder, write sidecar JSON, spawn
   `pw-record --raw --target <node> --rate 48000 --channels 1 --format s16 --latency 20ms take-001.raw`
   with `start_new_session=True` so it survives the UI. Store pid in the sidecar.
2. **While recording**: a thread stats the file every 200 ms. Bytes written → elapsed time
   and the level meter (RMS/peak over the newest bytes). No second audio stream needed.
   If the file stops growing for > 2 s while the process lives → show a red "stalled" warning.
   If the process dies → auto-restart into `take-002.raw`, mark a gap in meta, keep going.
3. **Pause**: SIGINT the process (clean close). **Resume**: new take file. Takes are
   concatenated at stop. Boundaries are logged with wall-clock times.
4. **Stop**: SIGINT, wait, verify `size == expected` within tolerance, then
   `ffmpeg -f s16le -ar 48000 -ac 1 -i concat... original.flac`, verify FLAC decodes to the same
   sample count, then delete the raw takes. Any failure in this chain leaves the raw takes in
   place and the item flagged "needs finalize".
5. **Startup recovery**: scan `recordings/*/takes/`. If a pid is alive → re-attach (show as
   recording, allow stop). If dead → offer/auto-run finalize. This also covers power loss.
6. **Guards**: refuse to start with < 1 GB free; warn at 10 min remaining at the current bitrate.
   Record at 48 kHz mono s16 by default (5.5 MB/min); stereo if the chosen source is stereo and
   the user asks.
7. **Monitoring**: before recording, a lightweight meter subprocess
   (`pw-record --raw ... -` piped to stdout) gives live levels for the selected source so you
   can check the mic. Optional "listen" toggle via `pw-loopback` for actual headphone monitoring.
8. **Source list**: from `pw-dump` / `pactl list sources` with friendly descriptions
   (your current sources: PCM2902 USB codec, FHD webcam, EasyEffects source, and monitors of
   outputs for capturing system audio).

## 4. Transcription pipeline (`echo-app _worker`)

1. Normalize: `ffmpeg -i original -ac 1 -ar 16000 -f wav normalized.wav` (honoring crop).
2. VAD: silero-vad (CPU, fast) → speech regions. Merge regions into windows ≤ 30 s, splitting
   at the longest internal pause; pad each window 150 ms.
3. Load base model once in bf16 with SDPA; load adapter with PEFT; `language="es"`.
   Adapter on/off is a job option (default on; the card says it helps mainly on degraded audio
   like phone voice notes, and is neutral on clean audio).
4. Batch windows (8–16 per batch on 10 GB), write each result to `transcript.json` as it
   completes. Jobs are resumable at window granularity.
5. Produce `transcript.txt` by joining windows; paragraph breaks where the VAD gap > 1.5 s.
6. Job queue: table `jobs(id, recording_id, kind, status, options, progress, error)`.
   The UI inserts jobs; the worker claims them. Worker started on demand by the UI, exits after
   N minutes idle. Logs to `~/.local/state/echo/worker.log`.

Throughput estimate on a 3080: roughly 30–60× realtime once loaded, so an hour of audio is a
couple of minutes. First-run download is ~4.3 GB.

## 5. UI (PySide6)

Three-pane window:

- **Left**: recording controls on top (source combo, level meter, Record / Pause / Stop, elapsed,
  disk remaining), library list below (title, date, duration, transcription status icon).
  The list accepts drag/drop of files and folders; drops from Dolphin, browsers, KDE Connect.
- **Center**: waveform (downsampled peaks cached per item) with playhead, crop handles,
  play/pause, seek, speed. Click a transcript segment to seek to its start time.
- **Right**: transcript editor. Plain text (QPlainTextEdit) backed by `transcript.edited.txt`,
  autosaved on idle. Buttons: Copy all, Export .txt/.md, Re-transcribe (base/adapter),
  Revert to model output. Segment timestamps shown in a gutter, toggle to hide.

Also a CLI (`echo-app record|import|transcribe|rescan|finalize`) built first, so each core piece is
testable headless and scriptable.

## 6. Milestones

| # | Deliverable | Scope |
|---|---|---|
| M0 | Skeleton | uv project with `uv.lock`, `.python-version`, `install.sh`, `echo-app doctor`, data dir, SQLite schema, `echo-app rescan`, config. Verify a clean install on a throwaway user account. |
| M1 | Recording engine + recovery | Steps in §3 as a library + CLI. Test: kill -9 the CLI mid-recording, restart, verify finalize produces the full audio. |
| M2 | Import | ffmpeg probe/copy/normalize; WhatsApp `.opus/.m4a/.amr` tested; duplicate detection by hash. |
| M3 | Worker + transcription | VAD, model load, batching, job queue, resumability. Benchmark on a long recording. |
| M4 | Qt UI v1 | Three panes, controls, meter, list, drag/drop, waveform + crop, player, editor, export. |
| M5 | Polish | Startup recovery UI, stalled/xrun warnings, idle worker shutdown, system tray "recording" indicator. |
| M6 (later) | Knowledge base | See §7. |
| M7 (later) | Speaker recognition | See §7. |

## 7. Future features and the hooks for them

**Knowledge-base correction.** Two complementary layers. First, in-model biasing: the decoder
context slot accepts text before the transcript. A sentence naming known people and terms
("En esta conversación se mencionan Surus y Mauro.") placed before the style primer made the
model spell them correctly in tests. The worker already accepts a `context` option per job and
records it in the transcript; the knowledge base only has to build that sentence. The engine
retries any passage whose output is implausibly short with simpler context, so a bad context
cannot silently drop speech. Second, post-hoc correction for what biasing misses:
- Glossary table: `terms(canonical, aliases[], kind=person|place|term, notes)`, editable in the UI.
- Pass 1 (deterministic): fuzzy + phonetic matching (Spanish-aware keys) of transcript n-grams
  against the glossary, applied only above a confidence threshold, each replacement logged in
  `corrections.json` with before/after/term id so it is auditable and reversible.
- Pass 2 (optional LLM): local or API model given the glossary and a window, asked for a
  minimal diff. Same logging.
- Hook today: raw model output in `transcript.json` is immutable; edits and corrections are layers
  on top. Re-running correction never touches raw output.

**Speaker recognition.** Not in this model. Bolt-on later: speaker embeddings (e.g.
`speechbrain` ECAPA or `wespeaker`) per VAD segment, cluster, label. Our VAD-segment design
already gives the per-segment boundaries this needs. Known-speaker matching can reuse the
knowledge base (`person` entries with enrolled voice embeddings).

## 8. Open points for you

1. Data dir: `~/.local/share/echo` or something under `~/Audio`?
2. ~~Accept the terms on both Hugging Face repos and log in before M3.~~ Done: token present at `~/.cache/huggingface/token`.
3. Default source: the PCM2902 USB codec, presumably. Should EasyEffects' processed source be
   selectable by default too? (It is in the list either way.)

## 9. Packaging, installation, and dependency risk

Goal: install on a fresh machine with one command, touch nothing owned by root, and get the
exact same dependency set every time.

### 9.1 What lands where

| Thing | Location | Owner |
|---|---|---|
| `uv` binary | `~/.local/bin/uv` (standalone installer) or `dnf install uv` (it is in Fedora repos) | the only bootstrap step |
| CPython 3.14 | `~/.local/share/uv/python/…` downloaded by uv; `.python-version` in the repo pins it; `python-preference = "only-managed"` in `pyproject.toml` so uv never picks up `/usr/bin/python3` | uv |
| All dependency wheels | `<clone>/.venv` | `uv sync --locked` (with `no-build = true` in `pyproject.toml`) |
| Launchers | `~/.local/bin/echo-app` (symlink to `bin/echo-app` in the clone), `~/.local/share/applications/echo-app.desktop`, icon in `~/.local/share/icons` | `install.sh` |
| Model weights | `~/.cache/huggingface/hub` (shared with other HF tools; token already there) | `echo-app models download` |
| Data | `~/.local/share/echo` | the app |

Uninstall = delete the clone, the three launcher files, and optionally the data dir and HF cache.
Nothing under `/usr`, nothing in site-packages of the system interpreter.

### 9.2 Reproducibility

- `uv.lock` is committed and carries sha256 hashes for every wheel. `uv sync --locked` fails
  loudly if `pyproject.toml` and the lock disagree, so a new machine gets byte-identical packages.
- `--no-build` refuses source distributions, so no `setup.py` from a third party ever runs at
  install time. Everything we need ships as wheels (checked today for 3.14 on x86_64 Linux).
- Two install profiles from one package:
  `uv sync --locked` → UI + recorder only (PySide6, numpy; ~400 MB).
  `uv sync --locked --extra worker` → adds torch, transformers, peft, silero-vad (~3.5 GB,
  CUDA libraries are inside the torch wheels, so the host only needs the NVIDIA driver).
  A recording-only laptop can run the first profile and share the data dir via Syncthing or
  similar; the GPU desktop runs the worker. The job queue is a file in the data dir, so
  nothing else changes.
- Dependency updates are a deliberate `uv lock --upgrade` + test + commit, never implicit.
- Keep the dependency list short and review it with `uv tree` before each lock update. Current
  direct deps: PySide6-Essentials, PySide6-Addons, numpy; extra `worker`: torch, transformers,
  peft, silero-vad, soundfile. No `accelerate` (we call `.to("cuda")` ourselves), no
  `torchaudio`, no `librosa` (ffmpeg does all decoding and resampling).

### 9.3 Model supply chain

- Both HF repos are referenced by **commit hash** in `echo`'s config, not by branch. An upstream
  push cannot change what you run.
- `use_safetensors=True` everywhere; the loader refuses pickle checkpoints.
- No `trust_remote_code`. `CohereAsrForConditionalGeneration` is in transformers proper.
- `HF_HUB_DISABLE_TELEMETRY=1` always; `HF_HUB_OFFLINE=1` once `echo-app doctor` confirms the pinned
  revisions are cached, so the worker never hits the network at run time.
- silero-vad: load the ONNX/JIT file from the pip package, not via `torch.hub` (which clones a
  git repo at run time).

### 9.4 System prerequisites (distro packages, checked by `echo-app doctor`)

| Need | Fedora package | Note |
|---|---|---|
| PipeWire capture | `pipewire-utils` (`pw-record`, `pw-dump`, `pw-loopback`) | Default on Fedora KDE. Fallback path if missing: GStreamer `pipewiresrc` via `gst-launch-1.0`, same raw-PCM contract. |
| Decode/encode | `ffmpeg` | `ffmpeg-free` from Fedora proper covers Opus, AAC, MP3, FLAC, WAV (all WhatsApp `.opus`/`.m4a`). AMR needs RPM Fusion's `ffmpeg`. `doctor` reports which codecs are present. |
| GPU | NVIDIA driver ≥ the version the locked torch CUDA build needs | Already installed (615.x). The only hard root-level prerequisite besides the above. |
| Desktop libs for Qt | xcb/wayland client libs | Present on any KDE/GNOME install; `doctor` runs a headless Qt probe to confirm. |

`echo-app doctor` prints a pass/fail table for all of the above plus: Python version matches
`.python-version`, lock is in sync, free disk, HF token present, pinned model revisions cached,
CUDA visible to torch (worker profile only).

### 9.5 Options considered and not chosen (for now)

- **Worker in a rootless Podman container** with CDI GPU access. Strongest isolation of the
  torch stack, but it needs `nvidia-container-toolkit` (root install) and CDI/SELinux setup per
  machine, and the image is ~8 GB. The file-based job queue means the worker can move into a
  container later without touching the UI. Revisit if the uv venv ever feels too exposed.
- **vLLM serving** the model behind its OpenAI-style transcription endpoint. Would shrink the
  app's deps to an HTTP client, but LoRA support for this model in vLLM is unverified, the
  adapter would have to be merged into a second 4.2 GB copy of the weights, and vLLM's own
  dependency tree is larger than ours. Not worth it for one user.
- **Flatpak**: good sandbox for the UI, but CUDA inside Flatpak is painful and the recorder
  needs raw PipeWire access anyway.
- **Distro Python packages** (`python3-pyside6`, `python3-torch`): Fedora's torch is CPU-only
  and both would tie us to the distro's versions. Rejected.

## 10. Quality bar: "a finished, lean app, not a side project"

This is the acceptance standard for every milestone. Lean means few features done completely,
with defaults that work and no knobs that exist only because they were easy to add. Finished
means a stranger could install it and use it without reading this file.

### 10.1 First run
- `install.sh` ends with the app in the KDE launcher, an icon, and a one-line "run `echo` or
  open it from the menu". No further steps.
- First launch: a single welcome pane that picks the default mic (pre-selected to the system
  default), shows the live meter, and offers "Download transcription model (4.3 GB)" with a
  progress bar. Skipping it still gives a fully working recorder; the transcribe button then says
  what is missing and offers the download.
- Startup under one second to an interactive window. The worker and torch never load in the UI
  process.

### 10.2 Everyday behavior
- Single instance. Launching again focuses the existing window.
- Record with one click or one key (`R`). Space play/pause, `Esc` stop, `Del` with confirmation.
  Every action has a shortcut and a visible label; no hidden gestures.
- Recording state is unmistakable: red indicator in the window title and the system tray, elapsed
  time, meter moving. Closing the window while recording asks once and offers "keep recording in
  background".
- No modal dialogs for routine work. Status and non-fatal errors appear in a one-line status bar
  with a "details" link. Fatal errors name the file and what to do next.
- Empty states say what to do ("Drop audio here or press R to record"), not "No items".
- Transcription progress is per item in the list (percent and ETA), and the app stays usable
  while it runs. Finished items get their transcript without a click if they are selected.
- Editor: autosave on idle, undo/redo, find, and a visible "edited" marker versus model output.
  Copy-all puts clean text on the clipboard, no timestamps unless the gutter is on.
- Every long operation (import, finalize, transcribe, download) is cancellable and survives an
  app restart.

### 10.3 Robustness you can see
- After a crash or power loss, the next launch recovers silently and shows the recovered item
  with a small "recovered" tag. No wizard, no questions.
- `echo-app doctor` is also a Help menu entry that renders the same table. Problems link to the fix.
- Disk and GPU memory problems are detected before they bite: refuse to start recording under
  1 GB free, and the worker reports "not enough GPU memory, close X" instead of a traceback.

### 10.4 What lean rules out
- No plugin system, no theme settings, no per-user profiles, no cloud sync, no accounts.
- Settings fit on one page: data directory, default source, sample rate, adapter on/off,
  worker idle timeout. Everything else is a sane constant.
- No feature ships half-done behind a flag. If crop is in, it has handles, snapping to silence,
  keyboard nudging, and export. If it is not that, it waits.
- Dependencies stay as listed in §9.2. Adding one needs a reason written in this file.

### 10.5 Fit and finish
- Follows the KDE/Breeze palette and system font; dark and light both tested.
- Consistent terminology: "recording" for items, "transcript" for text, "source" for input.
- Window layout, pane sizes, last selection and scroll position persist between launches.
- Version string, changelog and an About box. Logs in `~/.local/state/echo/` with rotation.
- Each milestone's PR includes a short screen recording of the feature as the user sees it.

### 10.6 Definition of done per milestone
A milestone is done when: the feature works on a clean install on a second user account; the
kill-and-recover test passes where recording is involved; `echo-app doctor` is green; there are no
TODO strings or debug output visible in the UI; and the items in §10.1–10.5 that apply to the
milestone are met. Milestones are re-scoped down rather than shipped partially.
