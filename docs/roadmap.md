# Echo roadmap

Where Echo could go next, as three prongs that can advance independently: **transcription
quality** (the AI layer), **adoption** (install anywhere, run on any hardware) and **product**
(what the app does with the recordings). Each prong lists concrete changes, what they depend on
and why they are ordered as they are. Each change that goes ahead becomes an OpenSpec change in
`openspec/changes/` as usual.

## Where Echo stands

Echo already does its core job completely: crash-safe recording, import, long-form Spanish
transcription on an NVIDIA GPU, an editor and search. Three things about the current code
shape this roadmap:

- **The model already accepts biasing text.** `worker/asr.py` puts a style sentence in the
  decoder's context slot, and `worker/service.py` passes a per-job `context` string through to
  it. Nothing in the CLI or the window sets that string yet. A dictionary of people and terms is
  therefore mostly plumbing, not model work.
- **The Linux-only surface is small and concentrated.** PipeWire tools (`audio/pipewire.py`,
  `audio/playback.py`, `audio/monitor.py`), POSIX signals and `/proc` (`recorder.py`),
  `fcntl` locks (`fsutil.py`, `transcription.py`, `recorder.py`), XDG paths (`paths.py`) and
  the freedesktop trash (`library.py`). Everything else is portable Python, Qt and ffmpeg.
- **Compute is one hard-wired profile.** The `worker` extra resolves torch from PyPI, which
  bundles CUDA on Linux and Windows. The engine already has a CPU path (float32, batch size 1,
  `use_gpu=False`) but nothing installs or chooses it, and it has never been measured.

The principles in `docs/design.md` (no lost audio, plain files, lean, no root) stay the test
for every item below.

## Prong 1: Transcription quality

### 1.1 Known people and terms: the dictionary

The question of whether this lives in the model or in the app has a clear answer: both, as
layers with different guarantees, and the app controls all of them. The guiding rule is that
the dictionary grows from work the user already does, in the editor, and never asks through a
dialog or a form.

**Where entries come from (app layer).**

- **Corrections.** When an edit is saved, Echo diffs the edited text against the model text. A
  replaced word that is capitalized, or that appears more than once across the library, is a
  candidate. A small chip under the editor offers "Add Surus to the dictionary"; one click adds
  it, dismissing mutes that word for good. The model's wrong spellings ("surus", "Zurus") are
  stored as aliases of the entry at the same time.
- **Titles.** Capitalized words the user types into a title are candidates the same way, since
  recordings get named after the person or the topic.
- **An optional line of context.** Under the title, a placeholder "Who is speaking, what
  about". Ignored by most recordings; when filled, it goes first in that job's context.
- **Settings → Dictionary** is the one place to see the whole list and remove or merge entries.
  It is for repair, not for data entry.

The file is `~/.config/echo/glossary.toml`: plain text, hand-editable, entries of two kinds
(`people` and `terms`) with a canonical spelling and aliases.

**How entries are used.**

*Layer A, in-model biasing (model layer, driven by the app).* The dictionary becomes the
`context` sentence, for example "Personas: Mauro, Lucía Fernández. Términos: PipeWire, Surus."
placed before the style sentence as `build_context` already does. The model spells names from
the prompt instead of guessing. The prompt is short, so entries go in most-recently-used first
up to a cap. The engine's existing retry (a passage that comes back implausibly short is redone
with the style sentence only, then with no context, keeping the fullest result) is the safety
net against a context sentence breaking output, so no separate evaluation tooling is needed;
one case in `tests/test_model_smoke.py` ("a dictionary sentence does not drop speech") covers
the regression. The request path (`transcription.request`) builds the sentence and stores it
in `transcribe.requested`; the worker and the provenance in `transcript.json` already do the
rest. `echo-app transcribe --context "..."` for the CLI.

*Layer B, post-hoc correction (app layer).* For what biasing misses, a pass over the finished
model transcript replaces the user's recorded aliases, and high-similarity matches of
multi-token names, with the canonical spelling. It works on a copy (the model output in
`transcript.json` stays immutable), logs each (position, before, after) so every replacement
is underlined in the editor and can be undone, and is conservative: never single common words.
Because it runs in the UI process in milliseconds, a new alias is applied to existing
transcripts immediately, without re-transcribing and without asking.

*Layer C, a personal adapter (model layer, long term).* PEFT is already in the environment.
Training a small LoRA on the user's own corrected transcripts is feasible on the same 8 GB GPU
and is the only way to fix systematic errors (an accent, a recurring domain) that prompting
cannot. It needs hours of corrected audio, and the model text and edited text that Echo already
keeps side by side are exactly that corpus. Not before layers A and B have been in daily use.

### 1.2 Speaker labels

The design doc already sketches this. Speaker embeddings per passage, clustered, with the
user naming clusters ("Speaker 1 → Lucía") and names kept in the same dictionary. Options:

- `pyannote` is the standard but adds a gated model and a heavier dependency tree.
- Embedding models shipped as ONNX (WeSpeaker, 3D-Speaker families) run on CPU through
  `onnxruntime`, fit the lean rule better, and would work on machines without a GPU.

Passages already have boundaries from VAD, so the minimum version labels passages rather than
words. Interviews and meetings are the use case; monologue recordings skip this entirely.

### 1.3 Other languages and code switching

The base model is multilingual; Echo fixes `LANGUAGE = "es"` and always loads the Spanish
adapter. A per-recording language setting (and "auto" from the model's own language
detection, if the processor exposes it) with the adapter applied only for Spanish is a small
change and widens the audience considerably. Mixed Spanish and English in one recording is a
harder case to try early.

### 1.4 Low-confidence marking

The retry logic in `asr.py` already identifies suspicious passages (implausibly short). Keeping
that signal, plus disagreement between the adapter and base-model outputs when both are run,
would let the editor shade passages the user should check first. Cheap and useful for long
recordings where nobody reads everything.

### 1.5 Summaries and structure (Echo Studio)

Titles, summaries, action items and chapter headings from a language model. These need a
second model, local or in the cloud, so they are not part of Echo: they belong to Echo Studio,
an optional extension installed into the same app (see Extensions in `docs/design.md`). Echo
provides the places Studio adds to and stays local. Markdown export with headings from markers
gives part of the value with no model at all (see Prong 3).

## Prong 2: Adoption

### 2.1 Ubuntu and Debian parity (now)

Ubuntu is already supposed to work and mostly does, with specific gaps:

- `doctor.py` and `install.sh` print Fedora fixes only (`sudo dnf install ...`). Detect the
  package manager (`/etc/os-release`) and print the apt, dnf or pacman line. The README's
  `libxcb-cursor0` note belongs in `doctor` as a check.
- Ubuntu 22.04 LTS runs PulseAudio for audio even though `pipewire-bin` can be installed, so
  `pw-record` finds no nodes. Either document "22.10 or newer" clearly, or let the PortAudio
  capture backend from 2.3 handle it.
- A GitHub Actions workflow running the fast test suite on `ubuntu-latest` and on a Fedora
  container, so the install profile and lockfile are exercised on both before each release.
- Tagged releases with a `CHANGELOG`, so "update" means `git pull` to a tag, not to whatever
  is on `main`.

### 2.2 Compute profiles: CUDA, CPU, ROCm

Today "with transcription" means "with CUDA". The clean way to add alternatives with uv is
one extra per profile and per-platform index pins:

```toml
[project.optional-dependencies]
cuda = ["torch>=2.10", ...]
cpu  = ["torch>=2.10", ...]
rocm = ["torch>=2.10", ...]

[tool.uv]
conflicts = [[{ extra = "cuda" }, { extra = "cpu" }, { extra = "rocm" }]]

[tool.uv.sources]
torch = [
  { index = "pytorch-cpu",  extra = "cpu" },
  { index = "pytorch-rocm", extra = "rocm", marker = "sys_platform == 'linux'" },
]
```

with `[[tool.uv.index]]` entries marked `explicit = true`, all still hash-locked and wheels
only. `install.sh --with-transcription=cpu|cuda|rocm` records the profile as it does now, and
`doctor` reports which one is installed and whether the hardware matches.

**CPU.** The engine's CPU path exists but is unmeasured. A 2 B-parameter encoder-decoder in
float32 needs about 8 GB of RAM and will be far slower than the GPU; whether it is "an hour of
audio overnight" or "an hour in an hour" decides whether the CPU profile is a real option or a
fallback. Work, in order:

1. Measure on a typical 8-core desktop with a few real recordings. Record the numbers in `docs/design.md`.
2. Dynamic int8 quantization of the linear layers (`torch.ao.quantization.quantize_dynamic`)
   is a one-line change that usually gives a large CPU speedup; bf16 on CPUs with AVX-512 BF16
   or AMX is a second knob. Both are checked against the same recordings for accuracy.
3. The CPU wheel of torch is about 200 MB instead of 3.5 GB, which makes the CPU profile the
   natural default for laptops and the base for Windows and macOS.
4. Decided: no alternative or smaller models. Quality matters more than throughput, and a
   second engine would mean testing and maintaining other models. Echo keeps one model and
   makes it run as well as it can on each device; long CPU jobs are already resumable and
   cancellable, and the user is told the measured speed before queueing. Revisit only if the
   measured CPU speed makes the profile useless in practice.

AMD CPUs need nothing special: the CPU wheels run on any x86-64. "AMD" as a GPU means ROCm,
which PyTorch ships as Linux wheels on its own index and which the profile above covers; AMD on
Windows is immature in PyTorch and waits for that to change.

### 2.3 Windows

The biggest adoption step and the most work. The Linux-only surface listed above becomes a set
of small abstractions, each useful on Linux too:

| Today | Change |
|---|---|
| `pw-record` child process writes raw PCM | A capture backend interface with two implementations: PipeWire (unchanged, preferred on Linux) and PortAudio through `sounddevice` (Windows, macOS, PulseAudio-only Linux). The PortAudio backend captures inside the supervisor process, so the supervisor's own crash-safety (fsync every 2 s, takes, recovery) carries over; what is lost is surviving a crash of the capture process separately, which the design accepts. "Computer audio" on Windows is WASAPI loopback; its availability through the shipped PortAudio build must be verified early, since it decides whether that feature ships on Windows at first. |
| SIGUSR1/SIGUSR2/SIGTERM for pause, resume, stop | A `command` file in the recording folder polled by the supervisor, next to the `status.json` it already writes. Simpler to test than signals and the same on every OS. |
| `/proc/<pid>/cmdline` to recognize a live supervisor | The supervisor writes its pid and a start token to `session.json`; liveness comes from the heartbeat in `status.json` that already exists (stale after a few seconds) plus a pid check. |
| `fcntl.flock` | A small lock module: `fcntl` on POSIX, `msvcrt.locking` on Windows. Three call sites. |
| XDG paths | A `paths.py` mapping to `%APPDATA%`, `%LOCALAPPDATA%` and the Known Folders on Windows, the Library folders on macOS. One module. |
| freedesktop trash | `send2trash` (tiny, pure Python, all three OSes). |
| `pw-play` for playback | ffmpeg still decodes; PortAudio output replaces `pw-play` on non-PipeWire systems. |
| `install.sh`, `.desktop` file | `install.ps1` (winget for uv and ffmpeg, Start Menu shortcut, `pythonw` so no console window) and `uninstall.ps1`. The `doctor` checks gain Windows equivalents. |

Sequencing inside this item: do the signal-to-file and lock changes first on Linux (they are
refactors with the existing tests), then the capture backend with the PipeWire implementation
still default, then the Windows pieces. A test run with the fake capture in `tests/` should
pass on Windows before any Windows-specific audio work starts. Decided: Windows ships with
microphone recording first; "computer audio" follows in its own change once loopback is
verified on a real machine, since the author has none. WSL2 is not a shortcut: there is
no PipeWire there and Qt windows under WSLg are second-rate, though "import and transcribe
only, on WSL2 with CUDA" could be documented as a stopgap for people who already live in WSL.

Combined with the CPU and CUDA profiles, Windows users get recording plus GPU transcription on
NVIDIA and CPU transcription elsewhere.

### 2.4 macOS

Nearly free once 2.3 is done: PortAudio covers the microphone, loopback needs a virtual
device (BlackHole) and is documented rather than built, torch has MPS wheels for Apple
silicon, and the paths and trash modules gain their third branch. Worth doing only after
Windows proves the abstractions.

### 2.5 Keeping the install lean while it grows

Three profiles times three OSes is a matrix that can erode "a short dependency list whose
every entry has a reason". Guard rails: the base profile stays PySide6 plus numpy plus
`sounddevice` and `send2trash`; every compute profile is one extra; CI resolves every profile
on every OS from the single lockfile so a broken combination fails before release.

## Prong 3: Product

Echo does what it says. The suggestions below keep it a recorder and transcript tool rather
than turning it into a note-taking platform, and most reuse existing pieces.

**While recording**
- **Markers.** A key (and the tray) drops a timestamped marker while recording. Markers show on
  the waveform and as anchors in the transcript; "jump to next marker" during playback. The
  cheapest way to find the important minute in a two-hour recording.
- **Global shortcut and quick note.** Start or stop a recording from any application. A "quick
  note" mode records until the key is pressed again and, when the transcript is ready, copies
  it to the clipboard: voice input for any text field, offline.
- **Auto title.** Title new recordings from the first sentence of the transcript when the user
  has not renamed them, instead of a timestamp.

**Library**
- **Tags and notes.** Free tags on recordings (stored in `meta.json`, indexed in SQLite, shown as
  filters above the list) and a short notes field. Enough structure for interviews, meetings
  and diary entries to live side by side.
- **Watched import folder.** A folder Echo imports from automatically (where WhatsApp exports or
  a phone sync land). Reuses the importer and its duplicate detection.
- **Dates and stats.** A calendar strip or month grouping in the list, and per-recording word
  count, speaking rate and silence share. Cheap, and it surfaces the "hours of voice notes"
  use case.

**Transcript**
- **Timestamps on demand.** Show passage start times in the margin; "Copy with timestamps";
  export to SRT and VTT (the segments already have what subtitles need) and JSON.
- **Edit with the audio.** A key to replay the passage under the cursor, and auto-pause while
  typing. Turns correction from a chore into a loop, and it feeds the dictionary (1.1).
- **Review mode.** Walk passages marked low-confidence (1.4) one by one, with the audio.
- **Richer Markdown export.** Headings from markers, paragraph timestamps as links, the dictionary
  people as a header. Export a whole selection or the whole library to a folder, so an
  Obsidian or any Markdown vault can hold the transcripts next to the audio.

**Interop and data**
- **Backup and sync guidance.** The data folder is already plain files; a short doc on syncing
  it (Syncthing, a mounted drive, the `data_dir` setting) and what happens to the SQLite cache
  (`echo-app rescan`) answers the first question every long-term user asks.
- **Open with Echo** from file managers is done on Linux; the Windows installer should register
  the same file associations.

## Sequencing

| Phase | Items | Why in this order |
|---|---|---|
| 0 | 2.1 Ubuntu parity; 2.2 profile skeleton with the CPU measurement | Small, independent, and the CPU decision depends on the measurement. |
| 1 | 1.1 dictionary (corrections chip, layers A and B); 2.3 Linux-side refactors (command file, locks, capture interface); 3 markers and timestamps export | The dictionary is the highest-value AI change and is mostly plumbing. The refactors de-risk Windows without touching behavior. |
| 2 | 2.3 Windows backend and installer; 2.2 CPU tuning of the one model, guided by the phase 0 measurement; 1.3 languages; 3 tags, watched folder, edit-with-audio | Windows is the long pole and starts as soon as the abstractions land. |
| 3 | 1.2 speakers; 2.4 macOS; 3 quick note, review mode, richer export | Each builds on phase 2 pieces. |
| Later | 1.1 layer C personal adapter | Needs a corpus; only worth it once the above is in daily use. |

## Decisions made

- **Quality over throughput.** One model, tuned per device. No alternative engines or smaller
  models; if the CPU profile proves too slow, that is revisited later with numbers.
- **Windows: microphone first.** "Computer audio" on Windows is a follow-up change that needs a
  tester with a Windows machine.
- **Product: all of it**, starting with markers, timestamps and subtitle export, and editing
  with the audio.
- **No evaluation tooling.** The engine's short-output retry is the safety net for the context
  sentence; one smoke-test case covers the regression.

## The plan as OpenSpec changes

`CLAUDE.md` at the repository root says how an agent picks, implements, verifies and
archives a change unattended. Each item is a change folder in `openspec/changes/`, ready to be applied in the usual way
(proposal, design where decisions were needed, spec deltas, tasks). The personal adapter has
no folder yet; it waits for the dictionary to be in daily use. Summaries are Echo Studio's
(1.5).

| Phase | Change | Prong | Status (2026-10-24) |
|---|---|---|---|
| 0 | `add-ubuntu-parity` | adoption | done; a real Ubuntu 24.04 and 22.04 pass is open |
| 0 | `add-compute-profiles` | adoption | archived |
| 1 | `add-dictionary` | AI | archived |
| 1 | `refactor-recorder-portability` | adoption | archived |
| 1 | `add-timestamps-export` | product | archived (done before markers, which reuse its margin) |
| 1 | `add-markers` | product | archived |
| 2 | `add-windows-support` | adoption | portable pieces and the PortAudio backend done; Windows runs open |
| 2 | `add-languages` | AI | archived |
| 2 | `add-tags-and-notes` | product | archived |
| 2 | `add-watched-folder` | product | archived |
| 2 | `add-low-confidence-marking` | AI | archived (done before edit-with-audio, which uses it) |
| 2 | `add-edit-with-audio` | product | archived |
| 3 | `add-speaker-labels` | AI | done; tuning on real interviews is open |
| 3 | `add-quick-note` | product | done; pressing the portal shortcuts on KDE and GNOME is open |
| 3 | `add-markdown-vault-export` | product | archived |
| 3 | `add-windows-loopback` | adoption | blocked: needs a Windows tester |
| 3 | `add-macos-support` | adoption | blocked: needs a Mac tester |
| 4 | `add-linked-recordings` | product | archived |
| 5 | `add-video-import` | product | archived |
| 5 | `add-agent-cli` | product | archived |
| 5 | `add-playback-volume` | product | archived |
| 6 | `add-call-recording` | product | done; a real call with headphones and an output switch are open |
| 6 | `add-speaker-naming` | AI | done; a check with real recordings of the user is open |
| 7 | `add-tag-categories` | product | archived |
| 7 | `add-speaker-search` | product | archived |
| 7 | `add-people-profiles` | product | archived |
| 7 | `add-speaker-merge` | AI | archived |
| 7 | `add-speaker-corrections` | AI | archived |
| 7 | `add-speaker-turns` | AI | done; a check on real meetings with interruptions is open |
| 7 | `add-speaker-relabel` | AI | done; a check on a real meeting is open |
| 7 | `change-silence-note` | product | archived |
| 7 | `add-call-turns` | AI | done; a check on a real call is open |
| 8 | `add-extension-points` | product | archived |
| 9 | `refine-window` | product | archived |
| 9 | `add-motion` | product | archived |
| 9 | `add-record-dock` | product | archived |
| 9 | `add-click-to-seek` | product | archived |
| 9 | `add-extension-screens` | product | archived |
| 9 | `add-extension-choice` | product | archived |

The open items are listed under "Blocked" in each change's `tasks.md`, with what a person has
to run and look for.

Dependencies: `refactor-recorder-portability` before `add-windows-support` and `add-markers`
(markers use the command file); `add-timestamps-export` before `add-edit-with-audio` and
`add-low-confidence-marking` (both use its alignment of edited text to passages);
`add-low-confidence-marking` before the review navigation in `add-edit-with-audio`; `add-dictionary` before `add-speaker-labels` (named people);
`add-markers` before the headings in `add-markdown-vault-export`.
`add-video-import` before `add-agent-cli` (meeting videos as inputs). Both serve the main use
case: long meetings recorded as screen recordings, transcribed from the window or by an agent.
`add-speaker-labels` before `add-call-recording` (speakers are clustered per track); its code is
in, so this does not wait for its archive. `add-call-recording` before `add-speaker-naming`
(the microphone track names the user).
`add-speaker-search` before `add-people-profiles` (a person's recordings come from its speakers table).
`add-speaker-turns` before `add-speaker-relabel` (it reassigns the cut pieces too); its code is
in, so this does not wait for its archive.
`refine-window` before `add-motion` and `add-record-dock`: both animate and reuse the parts it
lays out (the recorder block, the player dock). Under Wayland neither GNOME nor KDE keeps the
dock above other windows; KWin does on the user's request (see the guide).
