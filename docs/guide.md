# Using Echo

Everything Echo does, by task. The [README](../README.md) covers installing. Every action is in
the menu button at the top of the sidebar (☰, or F10), and all shortcuts are under Help →
Keyboard shortcuts (F1).

**The window.** The sidebar holds the recorder, the search and your recordings, grouped by day.
The selected recording shows its title, date and tags at the top, its transcript in the middle
and the player along the bottom. Details (the panel button at the top right, or Ctrl+I) opens
its notes, markers, context line, file, statistics and how the transcript was made; it stays
open or closed as you leave it. Messages show for a few seconds over the bottom of the window.

- [Recording](#recording)
- [Importing](#importing)
- [Transcripts](#transcripts)
- [Who said what](#who-said-what)
- [Names, people and tags](#names-people-and-tags)
- [Playing, cropping and linking](#playing-cropping-and-linking)
- [Searching and exporting](#searching-and-exporting)
- [Command line](#command-line)
- [Where things live](#where-things-live)
- [Troubleshooting](#troubleshooting)
- [Windows](#windows)

## Recording

**Record.** Press Record (Ctrl+R) and speak. The input's name is under the button; click it to
pick another, see its level, listen to it, set its gain or add the computer's audio. The waves
under the recorder rise with the input, and if it stays silent the name under Record says so.
While recording, the recorder shows the time, the level, Pause (Ctrl+Shift+R), Stop and a
marker button. Closing the window does not stop a recording: it carries on, with a tray icon to
stop it.

**Gain.** The slider under the level, in the input panel, is the input's gain: keep the loudest
parts out of the red (double-click for 100%). It is the same setting as the desktop's sound
settings, so it stays with the microphone; with PortAudio (no PipeWire) it is hidden and those
settings set it.

**Nothing is lost.** Recording runs in its own background process and is saved to disk every
two seconds. A closed window, a crash or a power cut loses nothing that reached the disk, and
the next start recovers the recording by itself. Finished recordings are lossless FLAC, kept
only after Echo checks they decode to exactly what was captured.

**Record a call.** With a microphone selected, turn on "Also record computer audio" in the input
panel: Echo also records what the default output plays (Meet, Teams, Zoom), and a second meter
shows it. Start the call, then Record.

- Wear headphones: with speakers the microphone hears the call too.
- Echo only listens, so the call app keeps its microphone and sound. If you switch outputs
  (headphones in, headphones out), the recording follows the default output.
- The recording is one FLAC file with two channels, your microphone on the first and the call
  on the second. Echo plays and transcribes them together, and speaker labels never mix you up
  with someone in the call (you are speaker 1). An exported file keeps the two channels.
- A noise gate or other effect chosen for Echo's microphone in the sound settings (Easy Effects,
  for example) applies to the microphone only.
- The choice is remembered; quick notes always record the microphone alone.

**Record from anywhere.** With Echo running (also in the tray), Ctrl+Alt+R starts or stops a
recording from any application, and Ctrl+Alt+N records a quick note: press it again to stop, and
when the text is ready it is on your clipboard. The first time, your desktop asks you to confirm
the keys. Where the desktop has no shortcuts portal, bind keys to `echo-app record --toggle` and
`echo-app record --quick-note` in its keyboard settings. Recordings you have not renamed take
their title from their first sentence.

**Recording dock.** Ctrl+Shift+D (or View → Recording dock) swaps the window for a small dock
that floats over other windows: Record, the time, a small wave that follows your voice, Marker
(with a count), Pause, Stop and a button back to the window. While recording, with the pointer
away for a few seconds it shrinks to the time; point at it for the rest. Problems such as a silent
microphone show in it in amber. After Stop it says the recording was saved and how the
transcription goes; Open shows it in the window. Closing the window while recording also shows
the dock. Drag it anywhere. Under Wayland, GNOME and KDE Plasma do not let applications stay
above other windows, so there the dock is a small normal window; Ctrl+Shift+D and the tray bring
it back. On KDE Plasma you can keep it above yourself: click the dock, press Alt+F3 and choose
More Actions → Keep Above Others, or add a window rule for the title "Echo recording".

**Markers.** While recording, press M, the marker button or the tray menu's entry to drop a
marker; type a short note if you like, without stopping. Markers show on the waveform, beside
the transcript and in Details, where a click plays from one; Alt+→
and Alt+← jump between them, Ctrl+M adds one at the playhead, and you can drag, edit or remove
them on the waveform.

## Importing

**Files and folders.** Drop audio or video files, or folders, on the window, use File → Import
(Ctrl+O), or open a file with Echo from your file manager. Duplicates are skipped.

- WhatsApp voice notes (`.opus`, `.m4a`, `.amr`) are recognized and dated from their names.
- From a video (`.mp4`, `.mkv`, `.mov`, …) Echo keeps one audio track (the default one; in OBS,
  the mix of all sources) and leaves the video where it is. The sound is copied as is when its
  format allows, which is the case for OBS and most screen recorders, and converted otherwise: a
  40-minute OBS meeting becomes a 57 MB recording in a few seconds, at full quality. OBS's file
  names (`2026-09-23 15-02-29.mp4`) give the title "Screen recording" and the date.

**Watch a folder.** Settings → Import → Add folder: new audio and video files that land there (a
phone sync folder, WhatsApp exports, OBS's recordings folder) are imported while Echo runs, once
they finish copying. The files stay in place. Without the window, `echo-app import --watch` does
the same.

## Transcripts

**Transcription.** New recordings and imports are transcribed automatically; progress and time
left show in the list, and you can keep recording and editing meanwhile. Speech is split at
natural pauses into passages and paragraphs, with punctuation and accents. A recent graphics card
transcribes an hour of audio in about a minute; a recent desktop processor in five to ten.

**Read and edit.** Click a recording. Edits save automatically and are never overwritten by a
new transcription. Copy with Ctrl+Shift+C or the Copy button (Ctrl+Alt+C with passage times),
find with Ctrl+F, export with Ctrl+E or Export. ⋯ → Passage times (Ctrl+T) shows when each
passage starts. While playing,
the current passage is highlighted, in edited text too. Click a word to move playback close to
it (half a second early, playing or paused); Ctrl+click a passage to play it from its start.

**Correct with the audio.** Ctrl+. plays the passage under the cursor (again to stop);
Ctrl+Alt+. and Ctrl+Alt+, move to the next or previous passage and play it; Ctrl+Shift+. goes to
the next passage to check. While a passage plays, typing pauses it, and a second after you stop
it plays again from its start (Settings → Editing turns this off).

**Check what matters.** Passages Echo is unsure of are shaded, with the reason on hover ("very
few words for 12 s of speech", "the model was unsure of it", "the model repeated itself here");
Details and the list count them (⚑). Editing a passage clears its mark.

**Other languages.** Spanish is the default. The transcript's menu (⋯ → Language) sets a
recording's language and transcribes it again; Settings → Transcription language changes the
default. The model handles Arabic, Chinese, Dutch, English, French, German, Greek, Italian,
Japanese, Korean, Polish, Portuguese and Vietnamese too; the Spanish adapter is used for Spanish
only.

## Who said what

In interviews, meetings and calls Echo tells the speakers apart, starts a new paragraph when the
speaker changes, and shows each speaker's name over their turn. It needs a small extra download (33 MB),
offered under Help → Transcription model. Monologues are left alone, and ⋯ → Label speakers
turns it off for a recording.

**Interruptions.** Someone cutting into another person's long paragraph ("¿y cuánto sale?")
becomes a paragraph of its own with their name. Echo catches most interruptions of a second or
more; in a recorded call it uses the two tracks to tell your side from theirs.

**Naming.** A bar over the transcript asks about one unnamed speaker at a time, whoever speaks
most first: ▶ plays a few seconds of them (the playhead and the text go there), then type a name
and press Enter, or click "Yes, Ana" when the voice matches someone you named before. "Not now"
stops asking about that recording; the names beside the text can still be clicked.

**You.** Answer "It's me" once (Echo asks your name, kept under Settings → Your name) and from
then on Echo names you itself, wherever it recognizes your voice and on the microphone side of
every recorded call. Other people are always suggested for you to confirm.

**Fixing labels.**

- *One person found twice:* click either name, choose "Same person as…" and the other. They
  become one speaker in that recording (exports, search and their profile follow); "Separate
  again" undoes it.
- *A paragraph given to the wrong person:* right-click it and choose Said by → the right person
  (or "Someone else…").
- *Someone cutting in mid-paragraph:* select their words first, then Said by. They become a
  paragraph of their own with their name, timed from where they fall in the passage (to a second
  or two).
- *Undo:* "Back to the speaker Echo found" undoes a fix; "Join with the paragraph above" removes
  a break.

**Echo learns from your fixes.** After a Said by, the other paragraphs that clearly sound like
the one you fixed follow it, and a message says how many moved; "Back to the speakers Echo
found" on a name undoes that. This works on recordings transcribed with Echo 1.2 or later. Fixes
are kept with the recording, also after transcribing again.

**Voices.** Naming someone teaches Echo their voice, once per recording: naming them again, or
transcribing again, does not count twice, and renaming a speaker takes back what the wrong name
learned. Voices are kept as numbers in `~/.config/echo/voices.json`, on this computer only.
Transcribing again finds the speakers afresh.

## Names, people and tags

**Dictionary.** When you correct a name in a transcript ("zurus" to "Surus"), a small suggestion
under the text offers to add it to the dictionary; one click, and Echo spells it that way in new
transcripts and fixes the old spelling in existing ones. Corrections Echo makes are underlined;
right-click one to undo it. "Not this word" stops the suggestion for good. Names typed into a
title are suggested the same way. The line in Details, "Who is speaking, what about", is
optional context for that recording. Settings → Dictionary lists everything for removing or
merging, and imports a list from a text file.

**People.** The People button at the top of the sidebar (Ctrl+Shift+P), or "Open profile" on a
speaker's name, lists everyone
Echo knows: people in the dictionary and everyone you named as a speaker. A profile keeps notes,
aliases (other spellings transcription corrects to their name) and tags; lists every recording
they speak in with how long they spoke (double-click to open it); plays a few seconds of their
voice; and forgets a voice Echo learned wrong. Profiles are files in the data folder
(`people/`), so they are backed up and synced with your recordings.

**Tags and notes.** Beside the date under the title, add tags ("+ tag", with completion); notes
are in Details. The filter button in the search field shows the most used tags as chips above
the list; click one to filter, click again to clear. While a tag filters the list its chips stay
shown. A tag with a
colon has a category: `client:Acme`, `project:Echo`, `type:standup`. A category's tags share one
chip ("client ▾") that lists its values and "Any client". A person's tags count for their
recordings: tag Ana `client:Acme` and `#client:acme` also finds every call she is in.

The list is grouped by Today, Yesterday, This week and then by month. A row shows the time or
day, the length and how many people speak; a status appears only when something is happening or
needs you (recording, transcribing, waiting, failed, not transcribed). Details shows a
recording's word count, speaking rate and share of silence. Settings → Appearance switches
between light, dark and the system's theme, and "Reduce motion" turns off the window's short
animations (Echo also leaves them off when the desktop has animations turned off).

## Playing, cropping and linking

**Volume and speed.** The speed button in the player steps through 1×, 1.25×, 1.5× and 2×. The
volume button opens a slider that goes up to 400% for quiet recordings; a limiter keeps loud
moments from distorting, and the button shows the volume when it is not 100%. Each recording
remembers its own volume. Click the percentage, or double-click the slider, to go back to 100%. Only playback changes: the audio
file, exports and transcription stay as they were.

**Crop.** Drag the edges of the waveform, or press `[` and `]` at the playhead; it snaps to
pauses, and Shift turns snapping off. Cropping changes nothing in the audio file. Transcribe
again to transcribe only the cropped part.

**Linked recordings.** Voice notes that are one long message (WhatsApp cuts them every few
minutes), or a recording you stopped and started again, can be linked into a set without merging
any audio. Select them (Ctrl+click or Shift+click) and press Link in the bar under the list, or
Ctrl+L, or drag one onto another. After importing notes that look like one burst, a line above
the list offers to link them in one click.

- A set is one row in the list (its arrow shows the parts). Selecting it shows the transcripts
  one under the other, each under its heading, and plays the parts back to back.
- Edit the text in place: each part keeps its own edits. Click a part's heading to open that
  part alone (to transcribe it again, crop it or add markers).
- Drag a part to reorder it (or Alt+Shift+↑/↓), drag it out of the set to unlink it, or
  right-click the set → Unlink. Copy and Export cover the whole set.

## Searching and exporting

**Search.** Ctrl+Shift+F (or Ctrl+K) searches titles, notes and transcript text of every
recording, ignoring accents. Opening a result shows its transcript with the words already found
(Enter or the arrows in the find bar step through them). Ctrl+F finds within the open
transcript. In the search:

- `#word` filters by tag; `#client:acme` is one value of a category and `#client:` any of them.
- `@ana` lists the recordings where a speaker named Ana talks (any word of the name, from its
  start: `@lopez` finds Ana López too; `@ana_lopez` asks for both words). `@ana precio` finds
  only what Ana said: each result shows her words, and opening it highlights them in her
  passages only. Typing `@` offers the names. Speakers you have not named are not found this way.

**Export.** Ctrl+E exports a transcript as text, Markdown, subtitles (SRT, VTT) or JSON, with
the speakers' names; subtitles and timed exports use your edited text, placed on the passages it
came from.

**Notes in a vault.** File → Export library to folder… writes one Markdown note per recording,
and one per linked set (title, date, tags as nested `#client/Acme` tags, people, markers as
headings, the text, a link to the audio), into any folder such as an Obsidian vault, and can
keep it up to date while Echo runs.

## Command line

Every core action also works from a terminal:

```text
echo-app                          open the window (files given are imported)
echo-app record [--wait] [--source NODE] [--title T] [--computer-audio | --no-computer-audio]
echo-app record --toggle          start a recording, or stop the active one
echo-app record --quick-note [--wait]   the same for a quick note; --wait prints its text
echo-app pause | resume | stop | status
echo-app mark [--note TEXT]       add a marker to the active recording
echo-app markers ID               list a recording's markers
echo-app sources                  list inputs (* marks the default)
echo-app import PATH...           import audio or video files, or folders
echo-app import --watch [FOLDER...] [--interval S]   keep importing new files (default: watched folders)
echo-app transcribe ID|FILE|FOLDER... | --all [--wait] [--again] [--format F [--out PATH]]
                  [--timeout S] [--json] [--no-adapter] [--context TEXT] [--language CODE]
echo-app info ID [--json]         one recording: transcript state, progress, speakers, files
echo-app cancel ID
echo-app list [QUERY] [--tag T] [--json]   list or search recordings (#word in QUERY is a tag,
                                  #category: any tag of a category, @name a speaker)
echo-app tag ID [+TAG ...] [-TAG ...]   show, add or remove tags
echo-app people [--json]          everyone Echo knows: recordings, aliases, tags and notes
echo-app link ID ID... [--title T]   link recordings into a set (a set id among them: add to it)
echo-app unlink ID                a set id dissolves the set; a recording id takes it out of its set
echo-app export ID [--format txt|md|srt|vtt|json] [--out PATH]   (ID may be a set's)
echo-app export --all FOLDER [--audio link|copy|none] [--timestamps]   Markdown notes for a vault
echo-app models download | status
echo-app recover                  repair recordings interrupted by a crash
echo-app finalize ID              retry saving a recording whose raw audio was kept
echo-app rescan                   rebuild the search index from the folders
echo-app doctor                   check the setup
```

`echo-app FILE` without a command opens the window, as the file manager's "Open with" does;
scripts use `transcribe` or `import`.

### From scripts and AI agents

`echo-app transcribe` takes audio and video files as well as recording ids, imports them, and
with `--format` waits and prints the transcript, speaker names included. It needs no window or
display and never asks anything, so it works over SSH and from an AI agent's shell:

```sh
echo-app transcribe meeting.mp4 --format md                  # the transcript on standard output
echo-app transcribe ~/Videos/meetings --format md --out ~/notes   # one file per recording
echo-app transcribe meeting.mp4 --format md --context "Lucía y Martín, presupuesto 2027"
```

- **Safe to repeat.** A file already in the library is its existing recording, and a recording
  that is transcribed, queued or running is not queued again (`--again` forces a new run). The
  same command run twice gives the same transcript.
- **Waiting with a limit.** `--timeout SECONDS` stops waiting and exits with code 3 while the
  transcription carries on in the background; running the same command again keeps waiting. An
  agent whose commands are cut off after a few minutes uses `--timeout 540` and repeats.
- **Output.** Standard output carries only the result; progress goes to standard error, as one
  line per stage and per 10% when it is not a terminal.
- **JSON.** `--json` on `transcribe`, `list` and `info` prints one JSON document. A recording has
  the same keys everywhere: `id`, `title`, `created`, `duration`, `source`, `tracks`
  (`["mic", "computer"]` for a recorded call, else null), `extracted_from`, `state`,
  `transcript_status` (`none`, `queued`, `running`, `done`, `failed`), `progress` (`stage`,
  `fraction`, `eta_s`), `error`, `language`, `speakers` (`count`, `names`), `tags`, `notes`,
  `folder`, `audio` and `files` (`transcript`, `corrected`, `edited`, absolute paths or null).
  `transcribe --json` lists each input with its `result`, `error`, the `output` file written and
  the `recording`. Keys are added in later versions, never renamed.
- **Exit codes.** 0 done (or queued, without waiting); 1 a recording failed, a file was not
  imported or not found, or transcription is not installed; 2 usage error; 3 timed out, still
  transcribing.

## Where things live

| What | Where |
|---|---|
| Recordings and transcripts | `~/.local/share/echo/recordings/`, one folder per recording |
| Settings | `~/.config/echo/settings.toml` |
| Dictionary of names and terms | `~/.config/echo/glossary.toml` |
| People's profiles (notes, tags) | `~/.local/share/echo/people/`, one file per person |
| Learned voices | `~/.config/echo/voices.json` |
| Logs | `~/.local/state/echo/` |
| Waveform cache | `~/.cache/echo/` |
| Models | `~/.cache/huggingface/hub/` |

A recording folder holds `audio.flac` (or the imported file, unchanged, or the sound of an
imported video), `meta.json`, `transcript.json` (model output with passage times),
`transcript.corrected.json` when the dictionary fixed something in it, and
`transcript.edited.txt` once you edit. Deleted recordings go to the desktop trash. Backing up or
syncing the data folder, and using it on two computers, is described in [sync.md](sync.md).

## Troubleshooting

Start with Help → Check setup, or `echo-app doctor`. It checks PipeWire and whether it owns the
audio devices, ffmpeg and its decoders, the libraries the window needs, the Python environment,
disk space, the GPU, the Hugging Face login and the model files, and gives the command for your
distribution that fixes whatever fails (including Ubuntu 22.04, where PulseAudio still owns
audio, and X11 sessions missing `libxcb-cursor0`).

- **The meter does not move.** Pick another input. If the meter reads "No sound for … s", check
  the cable, the mute switch and the input gain (the slider under the meter, or a knob on your
  audio interface). With a noise gate on the microphone that note comes and goes in every pause;
  that is the gate, and the recording is fine.
- **A recorded call has only my side.** Echo records the default output. Check that the call app
  plays to it (its audio settings, or "Same as system"), or make the call's device the default
  in the desktop's sound settings; the computer-audio meter moves when it is right.
- **A recorded call labels everyone as one side.** If both meters move together while only you
  speak, the computer audio is recording your microphone: in the desktop's sound settings, while
  recording, set "Echo computer audio" back to the default output's monitor. Echo transcribes
  such a call as from one microphone.
- **Old voice notes (`.amr`) do not import.** Fedora's `ffmpeg-free` lacks the AMR decoder;
  install `ffmpeg` from RPM Fusion. Doctor lists the missing decoders.
- **Transcription is slower than expected.** With less than about 5 GB of graphics memory free
  when transcription starts (a smaller card, or games and browsers holding it), Echo uses the
  processor instead; `echo-app doctor` shows which one it uses. Echo frees the GPU five minutes
  after its last transcription (configurable in Settings).
- **A recording shows "Needs attention".** Its raw audio is safe in the recording's `takes/`
  folder. Use "Try saving again" in the transcript panel, or `echo-app finalize ID`.

Logs are in `~/.local/state/echo/`.

## Windows

Windows support has not been tested on a real Windows machine yet; reports are welcome.
Recording uses the microphone ("Computer audio" is not available on Windows yet), and
transcription runs on an NVIDIA GPU or on the processor.

In PowerShell, from the cloned folder (no administrator rights needed):

```powershell
.\install.ps1 -WithTranscription        # or .\install.ps1 for recording only; -Compute cuda|cpu to choose
```

It installs `uv` and `ffmpeg` with winget if they are missing, adds Echo to the Start Menu, puts
an `echo-app` command on your PATH and adds "Open with Echo" for audio files. `.\uninstall.ps1`
removes all of that and keeps your recordings (`-Purge` deletes them too). Recordings live in
`Documents\Echo`, settings in `%APPDATA%\Echo`, logs and caches in `%LOCALAPPDATA%\Echo`.
