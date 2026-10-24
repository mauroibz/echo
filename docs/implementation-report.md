# Implementation report: the roadmap, 2026-10-24

Branch `roadmap` (local, not pushed, not merged into `main`). It starts with the plan squashed
into one commit authored by you ("Add the roadmap and its OpenSpec changes (final version of the
plan)"), followed by one commit per change, a fix commit after an independent review, and status
commits. No commit carries an AI co-author line.

Your installed Echo runs from this clone, so opening Echo now runs this branch. To go back:
`git switch main && ./install.sh`.

## Where things stand

| Change | Status |
|---|---|
| Ubuntu and Debian parity | Done. Open: a pass on real Ubuntu 24.04 and 22.04 machines |
| Compute profiles (CUDA, CPU, ROCm) | Archived |
| Dictionary of names and terms | Archived |
| Recorder portability refactor | Archived |
| Passage times and subtitle export | Archived |
| Markers | Archived |
| Windows support | Portable pieces and the PortAudio backend done. Open: everything that needs Windows |
| Languages | Archived |
| Tags and notes | Archived |
| Watched folders | Archived |
| Low-confidence marking | Archived |
| Editing with the audio | Archived |
| Speaker labels | Done. Open: tuning on real interviews |
| Quick note and global shortcuts | Done. Open: pressing the shortcuts on KDE and GNOME |
| Markdown vault export | Archived |
| Windows loopback, macOS | Not started: their plans say to wait for a tester |

Each open item is listed under "Blocked" in its change's `tasks.md` with exactly what to run and
what to look for.

Tests: 237 pass in the fast suite (6 opt-in hardware tests skipped). The hardware suites pass on
this machine too: real PipeWire kill-and-recover, real PortAudio recording and crash recovery,
and the real-model smoke tests on the RTX 3080.

## What each change does, and how it was checked

**Ubuntu and Debian parity.** Doctor gives every fix as the apt, dnf or pacman command for your
distribution, detects PulseAudio still owning the audio (Ubuntu 22.04), and checks the X11 cursor
library. There is a CI workflow (Ubuntu, Fedora, Windows), a `CHANGELOG.md`, and a local
`v0.1.0` tag on the public release. Running the Fedora job in a container found a real bug:
`./install.sh` failed with Fedora's own `uv` package, which turns off automatic Python downloads.
It now installs the pinned Python explicitly.

**Compute profiles.** `./install.sh --with-transcription` picks `cuda`, `rocm` or `cpu` from the
hardware. All three are in the one hash-locked lockfile, and the `cuda` set is identical to
before. On the processor the engine uses int8 linear layers, one thread per physical core, and
batches sized to free memory. Measured on this Ryzen 5 7600X against the GPU on 6, 21 and 62
minute recordings:

| | Speed | Agreement with the GPU |
|---|---|---|
| float32 (what existed) | 5× real time | 99.8 to 99.9% |
| bf16 | about 9.7× | 99.96 to 100% |
| int8, batch 4 (chosen) | 17 to 19× | 99.0 to 99.9% |

The production CPU path transcribes an hour in about six minutes. Doctor, the model dialog and
the transcript panel say how long transcription takes on this computer.

*Your call:* int8 was chosen because the spec says "fastest that passes 99%". bf16 is closer to
the GPU at half the speed. Switching is a one-line change in `worker/asr.py`.

**Dictionary.** It learns from your corrections. Fixing "zurus" to "Surus" shows a chip offering
to add it; one click adds it. After that, the model gets the name in its context, and existing
transcripts are corrected in a copy (`transcript.corrected.json`), each correction underlined and
undoable. Names typed in titles are offered too. There is a "who is speaking, what about" line
per recording, Settings → Dictionary, and `--context` on the CLI.

Checked on three audiobook chapters with the real model. One correction fixed 5 of 6 spellings
of "Villaamil" in chapter 1, with no re-transcription, and all 4 in chapter 2. That check also
found a gap, now fixed: a new misspelling of a name already in the dictionary is now learned as
another alias.

**Recorder portability.** Pause, resume and stop are command files; liveness is a token plus a
heartbeat; `locks.py` replaces the `fcntl` calls; and an audio backend interface sits in front of
PipeWire. Old signals still work, and a recording started by the previous version can still be
stopped. Checked with a two-hour real PipeWire recording with a pause: 7200.02 s, a verified
FLAC, the pause noted at 40:00.

**Passage times and subtitles.** A time margin (Ctrl+T), "Copy with timestamps", and SRT, VTT
and JSON export, all working on edited text through a new word alignment. Follow-along and
Ctrl+click now also work on edited transcripts, which they didn't before.

**Markers.** M while recording, the tray menu, or `echo-app mark --note`. Markers are flags on
the waveform (drag, edit, remove, Ctrl+M at the playhead) and dots beside the transcript; Alt+←
and Alt+→ jump between them. Real PipeWire put them at the right audio time across a pause.

**Languages.** Spanish plus 13 more, which is what the pinned processor accepts; the tokenizer
names more, but the processor refuses them. The Spanish adapter is used for Spanish only. Each
language was checked with a synthesized sentence on the real model. The Japanese clip failed,
but because espeak-ng reads kanji aloud as "Chinese letter", not because of the model.

**Low-confidence marking.** Passages that came back short, needed a retry, or that the model was
unsure of are shaded, with the reason on hover and counts in the list and status line. The
scores cost 1.3% of GPU time.

This work found a real gap in the safety net: with a dictionary sentence in the context, one
8-second passage became the confident fragment "Debido a que no se puede", which passed the
short-output check. Very unsure passages are now retried too, which recovered the sentence.

**Editing with the audio.** Ctrl+. plays the passage at the cursor; Ctrl+Alt+. and Ctrl+Alt+,
step to the next or previous passage; Ctrl+Shift+. jumps to the next passage to check. Typing
pauses the passage and replays it when you stop.

**Tags and notes.** Tags and a note under the title, tag chips that filter the list, `#tag` in
search, month headings, and word count, speaking rate and silence share. Also `echo-app tag` and
`list --tag`.

**Watched folders.** Settings → Import adds folders whose new audio is imported once it stops
changing. `echo-app import --watch` does the same headless.

**Windows.** Done here: Windows folders, `install.ps1` and `uninstall.ps1` (they parse in
PowerShell 7; they have never run on Windows), an icon, CUDA torch for Windows, and a PortAudio
backend. The backend is also used on Linux wherever PipeWire doesn't run the audio, and is
verified on this machine by forcing it: recording, pause, markers, crash recovery, meter and
playback.

**Markdown vault.** File → Export library to folder, or `echo-app export --all`: one note per
recording, markers as headings, a link to the audio, and optional sync while Echo runs. The
export never replaces a file it didn't write or one you edited. `docs/sync.md` explains backing
up and syncing.

**Quick note and global shortcuts.** Ctrl+Alt+R records and Ctrl+Alt+N takes a quick note, from
any application, through the desktop portal. A quick note's text goes to the clipboard when it's
ready. There are also `echo-app record --toggle` and `--quick-note`. Recordings you haven't
renamed take their title from their first sentence. Checked end to end with the real model: the
note's text was printed 4.9 s after stopping.

**Speaker labels.** A 27 MB ONNX speaker model, an optional download, run on the processor.
Speakers are labelled per passage, each change of speaker starts a paragraph, and names show
beside the text. A name you give is remembered as a voice and suggested in later recordings, and
exports carry the names.

Tuned on conversations built from nine LibriVox readers, also through a degraded shared channel:
thresholds 0.30 to 0.55 got everything right, and 0.4 is used. End to end, a name given in one
recording was suggested for the right speaker in another, made from a different chapter. Limit:
a passage that straddles a quick turn change gets one speaker.

## Things to know before you use it

- **On first start**, KDE asks you to confirm the two global shortcuts. That's the portal's own
  dialog; untick "Record from anywhere" in Settings if you don't want it.
- **New dependencies:**
  - In the base install: `sounddevice` (with `cffi`) and `send2trash`, plus `jeepney` on Linux.
  - In the transcription profiles: `onnxruntime` (with `flatbuffers` and `protobuf`).
  - Each has a stated reason in `docs/design.md`'s dependency table.
- **The speaker model** was downloaded into your Hugging Face cache (27 MB) for testing. Without
  it, speakers are simply not labelled.
- **Your library:** the index rebuilds itself at schema 2 on first start. It was tested on a copy
  of your real data: both recordings and their transcripts open, with no errors.
- **Nothing was pushed.** The `v0.1.0` tag is local too.

## The independent review

After the features were in, a separate reviewer read the whole diff. It found ten real problems,
and all ten are fixed in "Fix what an independent review of the branch found", with tests. The
worst were:

- Recovery could delete a recording that was still starting. This race was already on `main`,
  and the new shortcut made it easier to hit.
- Edits made during a recording (title, tags, notes) were lost when the recording was finalized.
- With PortAudio, a device that failed to reopen ended the recording.
- The vault export could overwrite a file of yours with the same name.
- A dictionary file that failed to parse once (for example mid-save) was moved aside, and then
  written over nearly empty.

One limit remains, for the Windows tester: a device that changes its sample rate in the middle
of a recording.
