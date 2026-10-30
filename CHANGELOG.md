# Changelog

Notable changes to Echo. Versions are git tags (`vX.Y.Z`); `main` may be ahead of the latest
tag.

## Unreleased

### Changed

- A calmer window with the same look. The menus are in a button at the top of the sidebar (F10)
  and messages show for a moment over the bottom of the window, instead of a menu bar and a
  status bar. At rest the recorder is Record and the input's name, which opens the input list,
  level, gain and computer audio; while recording it shows the time, the level, Pause, Stop and a
  marker button. The list is grouped by Today, Yesterday, This week and month, and a row shows a
  status only when something is happening or needs you. The selected recording has its title,
  date and tags on top, the transcript in a reading column with each speaker's name over their
  turn, and the player along the bottom; Details (Ctrl+I) holds the notes, markers, context line,
  file and statistics. Tag chips open from a filter button in the search field. In dark mode the
  transcript's text is softer and speakers' colors keep their contrast.

### Added

- Short animations where something changes: the recorder entering a recording, a pulsing dot
  (blinking amber when paused), a ring and a falling marker when you mark a moment, new
  recordings sliding into the list, a sweep along a running transcription, smooth scrolling to
  the passage that plays, Details sliding open and messages fading. Settings → Appearance →
  "Reduce motion" turns them off, and Echo leaves them off when the desktop has animations off.

## 1.3.0 - 2026-10-29

### Added

- Extension points for optional packages installed into the same app (the first planned is Echo
  Studio, for summaries). Without one, Echo looks and works as before and still sends nothing
  anywhere; `ECHO_NO_EXTENSIONS=1` starts it without any. See Extensions in `docs/design.md`.

## 1.2.0 - 2026-10-28

### Added

- Record both sides of a call. With a microphone selected, "Computer audio" also records what
  the default output plays, as a second track, without taking the microphone or the sound from
  the call app. The recording is one lossless FLAC with your microphone on channel 1 and the
  call on channel 2; it plays, draws and transcribes as one conversation, and speaker labels
  keep you (speaker 1) apart from the people in the call. A second meter shows the computer
  audio. From the command line: `echo-app record --computer-audio`; `info --json` reports
  `tracks`.
- Naming speakers without hunting for it. A bar over the transcript asks about one unnamed
  speaker at a time, with a few seconds of them to hear: a known voice in one click, anyone else
  by typing their name, or "Not now". Answer "It's me" once and Echo names you itself from then
  on, by your voice and on the microphone side of recorded calls. "Your name" is in Settings.
- Tag categories. A tag like `client:Acme` belongs to the category "client": the tag bar shows
  one chip per category with its values and "Any client", `#client:` searches the whole
  category, and Markdown exports write `#client/Acme`.
- Search by speaker. `@ana` lists the recordings where Ana speaks; `@ana precio` finds only what
  she said, shows her words under each result, and highlights them in her passages. Typing `@`
  offers the names. Works in `echo-app list` too.
- People. View → People (Ctrl+Shift+P), or "Open profile" on a speaker's name: notes, aliases
  and tags for each person, every recording they speak in with their speaking time, a sample of
  their voice, and "Forget voice". A person's tags find their recordings in search. Profiles
  are files in the data folder's `people/`; `echo-app people [--json]` lists them.
- "Same person as…" on a speaker's name joins two speakers Echo told apart wrongly into one,
  for that recording: labels, the naming bar, exports, search and profiles follow, and naming
  them teaches Echo both parts of the voice. "Separate again" undoes it.
- "Said by" in the transcript's right-click menu: give a paragraph to the right speaker, or
  select an interruption to split it off as its own paragraph with its own speaker. Undo it,
  join paragraphs, or add someone new. Fixes are kept with their times as data for improving
  speaker labeling.
- Short interruptions are found. When someone cuts into another person's long paragraph for a
  few words, that becomes its own paragraph with their name, instead of being labeled as the
  person around it. In a recorded call, the two tracks tell your side from theirs. Speakers are
  also merged into one less often. Needs a 6 MB download, offered under Help → Transcription
  model; transcribe a recording again to apply it.
- "Said by" teaches Echo the voice: after a fix, the other passages that clearly sound like it
  follow, and "Back to the speakers Echo found" on a name undoes it. Needs a transcript made
  with this version.

### Changed

- A recording teaches a person's voice once. Naming them again, or transcribing again, replaces
  what that recording taught instead of adding it again, and renaming a speaker takes back what
  the wrong name learned. Voices learned wrong this way before are best forgotten in the
  person's profile and named again.
- The "no sound from this input" hint is a note on the level meter in the sidebar, so a noise
  gate no longer makes the controls jump. The welcome screen keeps the full hint.
- The README is short; the full manual is [docs/guide.md](docs/guide.md).

### Fixed

- With a noise gate or another virtual source chosen for Echo's microphone in the desktop's sound
  settings, recorded calls had the microphone on both tracks: the audio server moved the
  computer-audio capture along with it. It now keeps to the default output. Calls recorded that
  way are labeled as from one microphone.
- The model sometimes got stuck repeating a word over and over, and the retry of an unsure
  passage could even prefer such a loop. A loop is now transcribed again, never kept from a
  retry, and if it stays it is cut to two repetitions and marked "the model repeated itself
  here".
- Pieces under 1.5 s cut out of a passage for an interruption often came back from the model as
  "Gracias."; that text is no longer shown.

## 1.1.0 - 2026-10-25

### Added

- Video files import as their sound. A screen recording or video call (`.mp4`, `.mkv`, `.mov`
  and more) becomes an audio recording with one track, copied without re-encoding when its
  format allows and verified; the video is left untouched and never copied. OBS file names give
  the title and date, and watched folders pick up videos too.
- A command line for scripts and AI agents. `echo-app transcribe` takes audio and video files
  (imported first) as well as ids; `--format` waits and prints the transcript; `--timeout`
  bounds the wait (exit code 3) without stopping the job; `--json` on `transcribe`, `list` and
  the new `echo-app info` prints machine-readable results; progress goes to standard error.
- A volume slider in the player, up to 400% for quiet recordings, with a limiter so the boost
  does not distort. Each recording and linked set remembers its own volume. Playback only: the
  audio file is unchanged.

### Changed

- `echo-app transcribe ID` no longer transcribes again a recording that already has a
  transcript, or one that is queued or running; add `--again` for a new run.

## 1.0.1 - 2026-10-24

### Changed

- Transcription no longer needs a large graphics card. On a card with less than about 5 GB free,
  or one older than the RTX 30 series, Echo transcribes on the processor instead of failing,
  and the installer picks the smaller processor build for cards under 6 GB. The README states
  the measured requirements (about 5 GB of graphics memory) instead of 8 GB.

### Fixed

- Stopping a recording adopted after a crash failed where nothing reaped the orphaned capture
  process (a container's first process): its zombie counted as running.
- Windows: saving any file failed (folder fsync), and free disk space could not be read.

## 1.0.0 - 2026-10-24

### Added

- `echo-app doctor` names the install command for the running distribution (apt, dnf or
  pacman), detects a session where PulseAudio still owns audio, and checks the X11 cursor
  library the window needs.
- Continuous testing on Ubuntu and Fedora.
- Transcription without an NVIDIA GPU: `./install.sh --with-transcription` now picks a build
  for an NVIDIA GPU, an AMD GPU (ROCm, untested) or the processor. On the processor Echo uses
  int8 weights and transcribes an hour of audio in about five minutes on a 6-core desktop.
  Echo says how long transcription takes on your computer once it has measured it.
- A dictionary of people and terms that learns from your corrections: fix a name once and a
  chip offers to add it; Echo then spells it right in new transcripts and fixes it in existing
  ones, underlining every automatic correction with one-click undo. An optional "who is
  speaking, what about" line per recording, `echo-app transcribe --context`, and Settings →
  Dictionary to tidy the list.
- Passage times: a margin with each passage's start time (Ctrl+T), "Copy with timestamps", and
  export to SRT and VTT subtitles and JSON, from the edited text too; `echo-app export`.
  Follow-along and Ctrl+click now work on edited transcripts.
- Markers: press M while recording (or use the tray, or `echo-app mark --note`) to mark a
  moment, with an optional note. They show on the waveform and beside the transcript, can be
  moved, edited and removed, and Alt+arrows jump between them.
- Transcription in 13 more languages besides Spanish (the transcript's menu, Settings, or
  `echo-app transcribe --language`); the Spanish adapter is used for Spanish only.
- Passages to check: Echo shades passages that came back short, needed a retry or that the
  model was unsure of, says why on hover and counts them. Passages the model was very unsure of
  are now retried, which recovers sentences a context sentence occasionally turned into a
  fragment.
- Correcting with the audio: Ctrl+. plays the passage at the cursor, Ctrl+Alt+. and Ctrl+Alt+,
  step through passages, Ctrl+Shift+. jumps to the next passage to check, and typing pauses
  the passage and replays it when you stop.
- Tags and notes on recordings, tag chips that filter the list, `#tag` in the search, month
  headings in long lists, and word count, speaking rate and silence share per recording;
  `echo-app tag` and `echo-app list --tag`.
- Watched folders: new audio files in chosen folders are imported automatically, in the window
  or with `echo-app import --watch`.
- Windows support, not yet tested on a real machine: `install.ps1` and `uninstall.ps1`, a
  PortAudio audio backend (also used on Linux where PipeWire does not run the sound), Windows
  folders, and CUDA or CPU transcription.
- Markdown notes for a vault: File → Export library to folder… and `echo-app export --all`, with
  markers as headings and an option to keep the folder up to date; `docs/sync.md` on backing up
  and syncing the data folder.
- Record from anywhere: Ctrl+Alt+R and Ctrl+Alt+N (quick note, copied to the clipboard when
  transcribed) through the desktop's shortcuts portal, `echo-app record --toggle` and
  `--quick-note`; recordings not renamed take their title from their first sentence.
- Speakers: interviews and meetings are split by speaker, with names you give remembered and
  suggested in later recordings, and carried into exports (needs a 27 MB model download).
- Ctrl+Shift+F searches all recordings, as in code editors (Ctrl+K still works), and opening a
  result shows its transcript with the searched words already found.
- An input gain slider under the level meter, usable while recording (PipeWire).
- Linked recordings: voice notes that belong together become one set, read with the
  transcripts one under the other, edited in place and played back to back, without merging
  any audio. Link a selection (Ctrl+L), drag one recording onto another, or accept the offer
  Echo makes after importing a burst of WhatsApp notes. `echo-app link` and `unlink`.

### Changed

- A new wordmark at the top left and on the welcome screen: "echo" with fading arcs spreading
  from its last letter, like an echo.

### Fixed

- `./install.sh` failed with Fedora's packaged `uv`, which turns automatic Python downloads
  off; it now installs the pinned Python explicitly.
- On KDE, a Plasma session started before the first install showed Echo without its icon until
  the next login; `./install.sh` now tells running KDE apps to reload their icons.

## 0.1.0 - 2026-10-24

First public release: crash-safe recording from any PipeWire input or the computer's own
audio, import with WhatsApp date recognition and duplicate detection, local Spanish
transcription on an NVIDIA GPU, an autosaving editor with follow-along playback, full-text
search, non-destructive crop, and the Lagoon look in light and dark.
