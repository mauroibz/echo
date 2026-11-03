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

**In the tray.** Settings → General, "Keep Echo running in the tray, and start it when you log
in", makes closing the window leave Echo in the tray (Quit in the tray's menu ends it) and adds an
entry to your desktop's autostart (`~/.config/autostart/echo-app.desktop`) that starts it without
its window. `echo-app gui --background` does the same by hand.

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
(with a count), Notes, Pause, Stop and a button back to the window. Notes (or N) drops a field
under the dock with the recording's notes, the same ones as in Details, saved as you type; Ctrl+T
in it writes the recording's time, as in `[12:34] price`, and the minutes then cover what was said
at that moment the way they cover a marker. While
recording, with the pointer away for a few seconds and the notes closed, it shrinks to the time;
point at it for the rest. Problems such as a silent
microphone show in it in amber. After Stop it says the recording was saved and how the
transcription goes; Open shows it in the window. Closing the window while recording also shows
the dock. To get it every time, turn on "Switch to the recording dock when a recording starts" in
Settings → General (quick notes leave the window as it is). Drag it anywhere. Under Wayland, GNOME and KDE Plasma do not let applications stay
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
an email (which matches them to a calendar's attendees, for extensions that read one), aliases
(other spellings transcription corrects to their name) and tags; lists every recording
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

## Echo Studio: your meetings, before and after

Echo Studio makes Echo a companion to your calendar and your meetings: it shows the next meeting,
records it when it starts, and turns each recording into minutes (a summary and action items you
can polish before they go to your team's tracker), with follow-up drafts and questions about your
recordings. Install Echo with `./install.sh --with-studio` (add it
to the transcription flag you used; `--without-studio` takes it out again). Without it Echo is
unchanged and sends nothing anywhere; `echo-app doctor` says whether Studio is loaded.

Summaries are written by a language model on a server you choose: one on this computer
(llama.cpp's `llama-server`, Ollama, vLLM, LM Studio), Anthropic, or another cloud provider
with an OpenAI-compatible API. In Settings → Summaries, enter its address (ending in `/v1`, for
example `http://127.0.0.1:8080/v1`, or `https://api.anthropic.com/v1` for Claude), the model's
name and, if it needs one, an API key; Test asks the server which
models it has. When the server is not on this computer or your network, the page says so: **the
transcript of each recording you summarize is sent to it,** as soon as it is ready unless you
turn automatic summaries off.

**The window.** Once a server or a calendar is set, a rail at the left holds Record at the top
(the coral waveform, Ctrl+R), then Briefing (Ctrl+1), Recordings (Ctrl+2: Echo's window as always)
People (Ctrl+3) and Action items (Ctrl+4). Record works from any page and records from the input chosen under Record in
Recordings; while it records, the rail shows the time under it, and pressing it again stops.

**Briefing.** At the top, the next meeting from your calendar: its time, title, invitation, who
is invited, Join the call, and whether it will record by itself (Don't record / Record it); while
recording, the time, your notes and who was invited. While a meeting is under way and not being
recorded, **Record this meeting** records it, named after it. Below, at the left, the minutes of your last
meetings as cards: the gist, the first action items with their owners and dates, your notes, who
was there, the tags and a star. Click a card to open it on its minutes, or its action items to
open those. At the right, Coming up:
the meetings of the next 7 days, by day, each with a switch for whether it is recorded when it
starts. Meetings with a video link start switched on (when "Record the meetings…" is on in
Settings → Calendar); one without, like an in-person meeting, starts off and can be switched on.
The Briefing only shows what your calendar and recordings say: no suggestions and no reminders.

**People.** Studio's People lists everyone Echo knows, by name or email. A person's page shows
their email (the key that matches them to calendar attendees), how many meetings and action items
they have, their meetings, the action items assigned to them, and your notes. "Aliases, tags and
voice…" opens Echo's People window.

Each meeting shows its minutes card and their part in it: a line on what they brought and the
points that make it up (what they reported, proposed, asked, objected to or took on). Star the
meetings worth finding again and tag them (the recording's own tags, so search finds them too);
the chips above the list show all of them, the starred ones or one tag. Their action items can be
checked off, switched on for the tracker and polished there as in a meeting's Action items. Each person's part comes from one more short request
per summary, for everyone named in it, and is kept in `parts.json` in the recording's folder; a
meeting summarized before this version has the line without the points until you summarize it
again. Stars are kept in `marks.json`.

**Action items.** The rail's Action items page lists the items not yet checked off from every
meeting, newest meeting first, under a heading per meeting (click it to open that meeting's Action
items). It works like a meeting's view, so you can clear last week's items without opening each
call: check them off, switch them on for the tracker, edit or discard them. Items you check off or
discard leave the page; the meeting's own view still has them. The filter at the top matches an
item's words, its owner and its meeting's title.

**Minutes.** Over the transcript, a Transcript / Minutes / Action items switch. Minutes shows the
selected recording's summary, with Summarize (Summarize again once there is one) and Copy. Its
action items have a view of their own, so neither is squeezed when the window is narrow; the
Action items tab shows how many are left to do. The summary is grouped by topic and ends with the next steps and who does them,
in the recording's language.

Each recording is summarized as soon as its transcript is ready, one at a time; uncheck "Summarize
each recording when its transcript is ready" in Settings → Summaries to summarize only when you
press the button. A recording you did not name then gets a short title from its summary instead
of its first sentence (uncheck "Give recordings you did not name a short title from their summary"
to keep the first sentence); a title you typed is never changed. If you edit the transcript
afterwards, the view says so. A transcript of more
than about an hour of talk (60,000 characters) is summarized in parts that are then joined.
Summaries are included in notes exported to a folder, under "Resumen".

Your notes and markers lead the summary: each note and marked moment is covered, expanded from
what was said around it, and editing a note marks the summary out of date.

Each summary's commitments also become action items, in the Action items view: each with a
checkbox, a title, a description
(what exactly and why, with the details that were said, so it stands on its own in a tracker), its
owner, the date it was promised for and a button that plays where it came up. They come from a
request of their own over the summary and the transcript, so they can include commitments the
summary's next steps leave out. Check an item off when it is done: it moves to the end, under a
"done" line where Show lists the checked-off ones. The check mark is yours: Echo never marks items late and does not
remind you. The pencil corrects the title, description, owner and date, adds context for whoever
picks the item up and a note only for you; the cross discards it (discarded items fold into one
line, where Show lists them with Restore), and Add writes one by hand. A person's page in People
lists the items assigned to them, to work on there too. After checking an item off, discarding it
or switching them all, a bar says what changed: **Undo** (or Ctrl+Z) takes it back for a few
seconds.

The lists work from the keyboard: click an item, or Tab into the list, then ↑ and ↓ (or J and K)
move between items, Space checks the current one off, T switches it for the tracker, E or Enter
edits it, Delete discards it (or restores a discarded one), and Ctrl+Z undoes. The items are kept in `actions.json` in
the recording's folder; summarizing again keeps your edits, context, notes, check marks, discards
and the items you added. Items from summaries made before
this version have no description until you summarize again.

**Sending them to your tracker.** Echo does not talk to Plane, Trello or Jira itself. Whatever
you use for that (an agent, a script, a scheduled sync) asks Echo for what you approved and tells
it what happened. Not every item belongs in a tracker, so nothing goes until you choose it: each
item has a **To tracker** switch, off to begin with. Switch on the ones that should go; until they
are sent you can still edit them or switch them off again. Discarding an item switches it off.
When most of a meeting's items should go, **Switch all on** in the bar above them switches every
open one on (done and discarded ones are left as they are); then switch off the few that stay.

When something sends them:
- Each item shows **✓ Sent · REF**, a link to it in the tracker, and can no longer be edited in
  Echo: from then on the tracker has it. You can still check it off.
- An item that could not be sent says why. Fix it and switch it on again.

When nothing else from a meeting should go to your tracker, press **Done with this meeting** in
the bar above its items (**Not done yet** takes it back). Once you have, and every item you
switched on is sent, the bar and the meeting's card on the Briefing say **✓ Processed**: you can
archive the call. A meeting with nothing to send is processed as soon as you press it. Each
control in the view says what it does when you point at it. Summarizing again never changes items
that are switched on or sent.

Follow-up, beside Copy, drafts the email you would send after the meeting: what was agreed and
who does what by when. Edit it, then Copy it or press Open in mail to start a message in your mail
program. Echo sends nothing itself. Read it first: a language model wrote it.

**Calendar.** In Settings → Calendar, paste your calendar's private address in iCal format, one
per line: in Google Calendar it is in the calendar's settings, "Secret address in iCal format"; in
Outlook or Teams, Settings → Calendar → Shared calendars → "Publish a calendar", the ICS link.
Test reads it. The address is a key to your calendar, so it is kept in your desktop's keyring
like the API key (or set `$ECHO_CALENDAR_URLS`); Echo only reads the calendar, every 10 minutes,
and works from the last copy when offline. The calendar works without a summaries server.

A recording made during a meeting (from 10 minutes before it) is that meeting's: if you did not
name it, it takes the meeting's title; transcription gets the attendees' names; the summary
knows who was invited and what the invitation says; and when you name a speaker like an
attendee, their profile learns the attendee's email. `echo-app calendar` lists the next
meetings (`--refresh` reads the calendar first, `--json` for scripts).

**Recording the meetings.** With "Record the meetings that have a video link when they start"
on (Settings → Calendar), a meeting with a Google Meet, Teams, Zoom or similar link starts
recording by itself when it starts, titled after it, and stops 10 minutes after it ends unless
you stop it first. A meeting is started once: stop it and it stays stopped. Switch a meeting off
in Coming up (or press Don't record on the next one) and it is left alone; switch one without a
link on and it records too. Echo has to be running, so turn on "Keep Echo running in the tray,
and start it when you log in" in Settings → General. Recording people may need their consent;
it is your call, as with the Record button.

The arrow beside Summarize picks the kind of meeting: a general one, or a template with its own
sections (`uno-a-uno`, `entrevista`, `clase`, `cliente`). The choice is kept as a tag such as
`template:entrevista`, so you can also set it in the tag field before the transcript is ready.
Your own templates are Markdown files in `~/.config/echo/studio/templates/` (the file's name is
the template's), with a line per rule on sections, for example "- Una sección por tema del
directorio, con las decisiones al final."; one named like a built-in replaces it.

From the command line: `echo-app summarize ID --print` prints the summary, `--all` summarizes
every transcribed recording that has no current summary (the ones from before you set up the
server, for example), `--json` gives the recording with a `summary` key, `--force` summarizes
again, `--template NAME` sets the kind of meeting, `--follow-up` prints the follow-up draft. Exit codes: 0 done, 1 a recording failed, 2 usage error, 3 no server set up. `echo-app doctor` checks the server.

Minutes and action items leave Echo through the command line, for a script, a scheduled sync or
an agent that loads them into your tracker: `echo-app meetings --since today` lists the
recordings with minutes, `echo-app minutes ID` prints one meeting's summary and action items, and
`echo-app actions --since 2026-10-01 --owner "Sofía Paz"` the items across meetings. Add `--json`
for scripts: each item carries its text, owner, date, time, your context and what was said around
it; discarded items are left out. `echo-app meetings --starred` lists the meetings you starred,
`--unprocessed` those not processed yet.

For whatever sends items to your tracker, `echo-app actions --ready --json` lists the items you
marked ready. Each has a `uid` that stays the same when you summarize again. After creating each
item, the sender runs `echo-app item ID UID --sent REF --url LINK`, or `--failed "why"` if it
could not. These are the only commands that write. `agents/echo/SKILL.md` in Echo's folder
explains all of them to an agent.

The server settings are in `~/.config/echo/studio.toml`. The key is kept in your desktop's
keyring (KDE Wallet or GNOME Keyring, through `secret-tool`), never in a file; to keep it
elsewhere, set `$ECHO_LLM_API_KEY` (for example from a `.env` you load) and Settings uses that.
Each summary is in its recording's folder as `summary.json`. `ECHO_NO_EXTENSIONS=1 echo-app`
starts Echo without Studio.

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
