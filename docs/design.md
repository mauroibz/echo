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
    meta.json                     title, source, created, duration, sha256, crop, gaps, markers,
                                  tags, notes, language, context line
    takes/take-NNN.raw            raw PCM, only while recording or awaiting finalize
    session.json, status.json     supervisor state and heartbeat, only while recording
    audio.<ext>                   recorded FLAC, the imported file byte for byte, or the sound
                                  of an imported video (meta.json's extracted_from names it)
    transcript.json               model output with passage times (replaced per run)
    transcript.corrected.json     the model output with dictionary corrections, each logged
    transcript.edited.txt         the user's text; the transcriber never writes it
    transcribe.requested          job marker with options
    transcribe.progress.json      written by the worker while it runs
    transcript.partial.json       finished passages, for resuming after a crash
    transcribe.error              last failure
  sets/<set id>.json              a linked set: title and member ids in order
```

Writes are atomic (temporary file, fsync, rename, fsync of the folder). Crop is stored as in
and out points in `meta.json`; the original audio is never changed. Deleting moves the folder
to the desktop trash.

A linked set (voice notes that are one message) is a file of its own rather than a field in each
member's `meta.json`: the member order lives in one place, reordering rewrites one small file
instead of several, and a recording folder still moves on its own. Members that are missing are
skipped, not removed, so a recording restored from the trash rejoins its set. A recording is in
one set at most; if two files claim it (a sync conflict), the newer file wins and the older
claim is dropped when that file is next written.

## Recording

1. `echo-app record` takes a per-data-folder lock (one recording at a time) and starts a
   detached supervisor, which runs `pw-record --raw` into `takes/take-001.raw`.
2. The supervisor fsyncs the take every 2 seconds and writes `status.json` on each state change
   and twice a second, also while it finalizes. Pause, resume and stop are command files; each
   resume starts a new take.
3. A marker is a `mark` command; the supervisor stores the position in the captured audio
   (bytes so far across takes, so pauses and gaps are excluded) in `session.json`, and
   finalize, also after a crash, copies the markers into `meta.json`.
4. If capture dies, the supervisor restarts it into a new take with backoff and records the gap.
   After repeated failures on the chosen input it falls back to the default input and says so.
   It warns when the take stops growing and refuses to start with less than 1 GB free.
5. On stop, the takes are encoded to FLAC. The FLAC is kept only if it decodes to exactly the
   captured PCM (sha256 of the decoded samples); then the takes are deleted. Any failure leaves
   the takes in place and the recording marked "needs attention".
6. On startup the window and `echo-app recover` look for interrupted recordings: a live
   supervisor is reattached, a `pw-record` still writing its take without a supervisor is
   adopted (its process exists and the take was written within 3 seconds), and if everything is
   dead the takes are finalized.

Measured PipeWire behavior this relies on: SIGINT and SIGTERM flush everything; a SIGKILL of
`pw-record` loses at most its 4 KB buffer (about 40 ms); a missing or unplugged target falls
back to the default input; `stream.capture.sink=true` captures what the computer plays.

Before recording, a low-rate `pw-record` stream drives the level meter while the window is
shown. After four seconds of exact digital silence Echo says so, because a connected
microphone with its gain up never produces it.

The gain slider sets the source node's own volume through `wpctl` (WirePlumber, installed with
PipeWire), the value the desktop's sound settings show. Echo does not scale samples itself:
PipeWire applies the volume before any reader, so the recording, the meter and other programs
all get the same input, and nothing about the recorder or its crash guarantees changes. `wpctl`
takes node ids, which change when a device returns, so the id is looked up by node name and
looked up again if setting fails. Monitors ("Computer audio") get no slider: their volume is the
speakers'. Up to 150%, PipeWire's software boost; past it there is mostly noise and clipping.

### Recording a call

With "Computer audio" on, the supervisor runs a second `pw-record` with no `--target` and
`stream.capture.sink=true`, which WirePlumber links to the default output's monitor and moves
when the default output changes. Reading a source or a monitor takes nothing from other
programs, so the call app keeps its microphone and its sound. The two captures form a pair of
takes, `take-NNN.raw` (the input) and `out-NNN.raw`, started together and stopped together
(signalled at the same moment from two threads; a capture frozen hard enough to ignore SIGINT
takes up to 5 s to kill, and the heartbeat goes on meanwhile so nothing takes the supervisor for
dead). If either dies or stalls, both end and a new
pair starts, and the gap is noted once; restarting only the failed one would leave the other
running across the gap with nothing to align it by. If the computer audio cannot start at all,
the input records alone with a warning. A crash adopts whichever captures still run; if only
one half survived, it is stopped and a new pair started. Elapsed time and markers keep counting
the input alone.

Measured on the development machine:

- Two captures on different devices (a USB microphone, a webcam microphone, the USB output's
  monitor and an HDMI output's monitor) grew by exactly the same number of samples over 300 s,
  47,998.27 per second each: PipeWire runs all streams on one graph clock and resamples each
  device into it. There is no drift to correct.
- The start can differ: a device woken from suspend began 299 ms after the others. Two captures
  started back to back on one output landed a click on the same sample in three runs of five
  and one 512-frame quantum (10.7 ms) apart in two, and in every run the files differed in
  length by exactly that offset, because SIGINT stops both in the same quantum.
- An idle output's monitor still delivers continuous silence, so the stall check works as is.

So a pair the supervisor stopped together (pause or stop, both running; marked `"align":
"end"` in `session.json`) is aligned at its end, which is exact whatever the startup delays
were; any other pair (one capture died first, or a crash) is aligned at its start, off by at most
the startup delay. The shorter take of a pair gets silence; nothing captured is trimmed. When
that silence goes on the input, markers and gap notes move with it.

Finalize interleaves the pairs into one two-channel FLAC (the input on channel 1, the computer
audio on 2) with `array` slices, an hour in 1.0 s, and verifies it as any recording: the hash of
the PCM fed to the encoder must match the decoded file. One file keeps crop, export, hashing and
"originals are never altered" unchanged. `meta.json` gets `channels: 2` and `tracks: ["mic",
"computer"]`; a two-channel file without `tracks` (an imported stereo file) is one source.
Playback, the waveform and the worker mix a call by summing the channels (`pan`), not by
ffmpeg's `-ac 1`, which averages them and would put each side 6 dB below its recorded level;
playback sends the sum to both ears through the limiter already used for the volume boost.

## Import

Files are probed with ffprobe, copied to a staging file, verified by hash and renamed into a new
recording folder unchanged. Duplicates are found by hash. WhatsApp names (`PTT-…`, `AUD-…`,
"WhatsApp Audio/Ptt … at/a las …", 12-hour and Spanish variants) give the recording its date.

A file with a real video stream (cover art, an attached picture, does not count) is imported as
its sound; the extension only decides which files a folder search considers. The track is the
one marked default, else the first: OBS's track 1 is the mix of every source and the others are
optional stems, so taking more would repeat voices. The format is decided, never asked:

| Track | Stored as | How |
|---|---|---|
| AAC, Opus, MP3, Vorbis, FLAC | `.m4a`, `.opus`, `.mp3`, `.ogg`, `.flac` | copied, no re-encoding |
| PCM | `.flac` | encoded, lossless |
| anything else (AC-3, E-AC-3, ALAC, WMA, …) | `.opus` | encoded at 128 kb/s, at most stereo |

Re-encoding a lossy track could only lose quality, so it is copied whenever an audio container
takes it; PCM stays lossless; for the rest Opus at 128 kb/s is transparent for speech. ffmpeg
writes to the staging folder, and a copy is verified by the packet hash of the source track
against the result (`-f streamhash`) or, when the container reframes the packets (ADTS AAC from
MPEG-TS into `.m4a`), by the hash of the decoded samples (`-f hash`); an encode must decode to
the source's length within 0.5 s. The video's own sha256, name, size, track number and method
go into `meta.json` as `extracted_from`, and duplicates are found by either hash, so a video
dropped twice is recognized before ffmpeg runs. The video is only read.

Measured on a 40-minute OBS meeting (H.264 with AAC 48 kHz stereo at 192 kb/s, 1.0 GB, file in
the page cache): `echo-app import` took 1.7 s from start to recording, of which hashing the video
0.7 s, copying the track 0.3 s and verifying 0.7 s; the result is a 57 MB `.m4a` with the same
2374.72 s. Hashing the decoded samples of that track takes 1.2 s. Transcribing it on the development GPU
took 57.6 s (model load included) and gave 124 passages, about 6,500 words and four speaker
clusters of 58, 48, 17 and 1 passages.

Watched folders (`watch_dirs` in settings) are scanned by `watch.py`, from the window (a
`QFileSystemWatcher` per folder with a 2-second debounce, plus a full look at start and every
five minutes) or from `echo-app import --watch` (polling). A file is imported once its size and
modification time have stayed the same for 3 seconds. `<data>/watch.json` remembers per folder
which files were handled, by size and modification time so they are not hashed again, and which
failed and why; a failure is reported once and retried only when the file changes.

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

Each recording has a language (`meta.json`, else the default in settings), stored in the request
and the transcript. The model's tokenizer has tokens for about 180 languages, but the pinned
processor accepts 14; `models.PROCESSOR_LANGUAGES` mirrors that list so the window can offer it
without importing transformers, and a test compares the two. The Spanish adapter is applied to
Spanish only, Spanish and English have a style sentence, and the others get only the dictionary's
context. Chinese and Japanese passages are joined without spaces and their words are counted as
two characters each for the short-output check.

The model's decoder accepts text in its context slot, though the model card does not say so.
Echo puts a style sentence there ("El texto que sigue está escrito en español correcto, con
mayúsculas, tildes y signos de puntuación."). In one 102-passage test chapter it cut the
passages transcribed without punctuation from 48 to 1. Naming people and terms there also fixes
their spelling. If a passage comes back implausibly short (under 0.4 words per second), it is
retried with the style sentence only, then with no context, so context can never silently drop
speech. The same happens when the model was very unsure of a passage (mean token log-probability
below -0.5; ordinary passages measured -0.01 to -0.17): with the dictionary's sentence in the
context, one 8-second passage came back as a confident-sounding fragment ("Debido a que no se
puede", -1.17) that had enough words to pass the first check, and the retry recovered the
sentence. The more confident text is kept.

Each passage in `transcript.json` (version 2) carries `flags` and its `logprob`: `retried`
(the kept text came from a retry), `short` (still short after the retries) and `low` (more than
1.5 standard deviations below the recording's mean log-probability, computed when the job ends;
fixed thresholds do not carry over between microphones). Asking `generate` for the scores cost
1.3% of GPU time on a 20-minute recording. The editor shades a flagged passage while its text is
still the model's, using the same alignment as the margin, so editing it clears the mark.

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

Measured on a 10 GB desktop card of the RTX 30 series: 20 minutes of speech in 18 seconds and
32 minutes in 23 seconds, including model load.

GPU memory, measured on that card with 28-second passages: the weights take 3.9 GB, and the
model peaks at 4.4 GB with one passage per batch and 5.0 GB with eight (the default), plus
about 0.4 GB the driver keeps. The engine halves the batch when memory runs out. With less than
4.8 GB free when the model loads, or on a card without native bfloat16 (older than the RTX 30
series, where emulated bfloat16 is slower than the processor), it loads on the processor
instead, and it does the same if loading on the GPU runs out of memory. The CUDA build of torch
runs on the processor too, so this needs no second install; the installer still picks the
processor build for cards under 6 GB, which is 4 GB smaller.

### On the processor

The same model runs on the CPU with the same planning and output. The engine there uses int8
weights for the linear layers (dynamic quantization; the LoRA layers stay float), one thread
per physical core, and batches of four passages when 6 GB of memory are free. Measured on a
6-core desktop processor (with AVX-512 BF16) against the GPU output on the same passages, with word
agreement in parentheses (lower case, punctuation ignored):

| Recording | GPU | float32 | bf16 | int8 | int8, batch 4 |
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

Tags are stored as typed in `meta.json` and compared folded (case and accents ignored), like
the search. The index (schema 2) has a `tags` table and puts the notes in the full-text body;
a schema change drops and rebuilds the index, so older installs pick both up on first start.
A tag's category is the text before its first colon (`client:Acme`), with text on both sides;
nothing about categories is stored apart from the tags, so there is nothing to migrate or keep
in sync. `#client:` matches the folded prefix `client:` in the `tags` table, so a plain tag
named `client` is not in the category. Markdown exports write `#client/Acme`, the nested form
Obsidian reads, since colons are not allowed in its tags.

Search by speaker uses two more tables (schema 4): `spoken`, full text of what each named speaker
said in each recording (the shown text, edited or corrected, cut into passages with
`align.cues` as the exports do), and `speakers`, who speaks where and for how long. Both come
from `meta.json` and the transcripts, so a rename or an edit re-indexes with the folder. `@ana`
is matched against the few names in `speakers` in Python (each `_`-separated word the start of
consecutive words of the folded name) and then filtered in SQL by exact names; with words, the
words must match `spoken` rows of those people, and FTS5's `snippet()` gives the line shown under
each result. The window passes the speaker numbers to the transcript, whose find keeps only
matches inside their passages. Only named speakers are indexed: "Speaker 2" is not a person.

### Speakers

After recognition the worker labels passages by speaker, on the processor: a voice embedding per
passage of 1.5 s or more (WeSpeaker's ResNet34 trained on VoxCeleb, Apache-2.0, a pinned 27 MB
ONNX file run with onnxruntime), Kaldi filterbank features computed in numpy (they match
torchaudio's `kaldi.fbank` to 1e-3), and agglomerative clustering on the cosine distance between
cluster centroids, stopping at 0.4. Shorter passages take the previous speaker; a "speaker" with
under 8 s of speech joins the nearest one; a recording with one speaker gets no labels. Each
speaker change starts a paragraph. The transcript keeps each speaker's centroid, and naming a
speaker stores it as that person's voice (`voices.json` next to the dictionary), so a later
recording suggests the name when a centroid is at least 0.85 similar.

Measured on conversations built from nine LibriVox readers (two to four speakers, 10 minutes
each), also passed through one shared phone-band, 12 kb/s Opus and noise channel: every
threshold from 0.30 to 0.55 found every speaker count and assigned all speech correctly; with
the shared channel, errors began at 0.60. Single-speaker recordings, the user's own desk
microphone among them, stayed one speaker even at 0.15. Chapters read by the same reader
measured 0.956 or more between centroids, different readers 0.72 at most. Embedding runs at
about 120× real time on a 6-core CPU. Labels are per passage, so a passage that straddles a turn
(the planner joins speech across pauses under 2 s) gets one speaker: in a two-reader test with
quick turns that was 27 s of 165 s.

A recorded call has its sides on separate channels, so each passage first goes to the track
that is louder over it (RMS, from the two channels decoded at 4 kHz, which is enough for
loudness and keeps an hour at 57 MB instead of 230 MB at 16 kHz), and voices are clustered
within each track. A voice in the room and a voice in the call are never one speaker, however
alike they sound, and the microphone's speakers are numbered first, so the user is speaker 1.
This assumes headphones: with speakers the microphone also hears the call.

Naming happens in a bar over the transcript, one unnamed speaker at a time, most speech first,
with 6 s of their longest passage to hear; asking per speaker is what makes a sample possible,
and naming a voice unheard is guessing. It waits while the dictionary's suggestion chip is shown
and never takes focus. "Not now" is stored as `naming_dismissed` in `meta.json`. The user's own
name is a setting (`your_name`) and their voice an ordinary `voices.json` entry. The worker names
the user, and only the user, in `meta.json`: in a call the one speaker on the microphone track
(certain, so that centroid is folded into the voice), otherwise the speaker it suggests as the
user (not folded back, so one wrong match cannot drift the voice). It never replaces a name the
user gave. Other people stay suggestions the user confirms: a name written silently and wrongly
into a transcript costs more than a click, and the 0.85 threshold was measured on audiobook
readers. The speakers record in the transcript notes `me` and, for calls, each speaker's `tracks`.

### Audio backends

All device access goes through `audio/backend.py`. PipeWire (its command-line tools) is used
wherever it runs the audio devices; elsewhere PortAudio through `sounddevice`
(`ECHO_AUDIO_BACKEND` forces one). With PortAudio the capture is a stream inside the supervisor
that a writer thread appends to the take, fsynced every two seconds by the supervisor's loop as
before; a supervisor crash loses at most those two seconds, and there is no capture process to
adopt, so recovery finalizes. A device that records only at its own rate (Windows' shared mode)
makes the session take that rate before any audio exists. PortAudio sources are named
`pa:<host API>:<device name>` and offer no "Computer audio" and no listening (yet). Measured on
this Fedora machine through PortAudio's ALSA layer: recording with pause and markers, and a
SIGKILL of the supervisor, which recovery turned into a verified recording of the audio so far.

## Command line for scripts and agents

`echo-app transcribe` is the scripted entry point: inputs are recording ids, or files and
folders that go through the importer (`DUPLICATE` resolves to the existing recording), resolved
all at once so a missing input stops the command before anything is imported or queued. A
recording whose transcript is done, queued or running is not queued again without `--again`;
together with duplicate detection this makes a rerun after a timeout cost nothing. `--format`
waits and renders through `export.render_transcript`, the same text the window exports.

Waiting polls the recording's files every 0.5 s, as the window does; the worker stays a separate
detached process, so `--timeout` only stops the waiting (exit code 3). Results go to standard
output and everything else to standard error, where progress is a redrawn line on a terminal
and otherwise one line per stage change and per further 10%, so a captured log stays short.
Before importing, the command checks that transcription and the models are installed.

`cli_json.record` builds the one dictionary every `--json` output uses for a recording (`list`,
`info`, and `transcribe` nested under each input's `recording`); its key list `KEYS` is pinned by
a test, since scripts depend on it. None of these commands imports Qt; a test runs them in a
process without display variables and checks `PySide6` was never loaded.

Measured as an agent runs it, with no display variables, on the 40-minute meeting video from
the import section and an empty library: `echo-app transcribe <video> --format md --timeout 540`
exited 0 after 57 s with the Markdown transcript on standard output and 35 lines on standard
error (imported, queued, then the stages `loading`, `detecting`, `transcribing` with time left,
and `speakers`, each in steps of about 10%). The same command again took 0.6 s, queued nothing
and printed the identical transcript.

## Window

PySide6 (`PySide6-Essentials` only). Playback is ffmpeg piped into `pw-play`, which avoids
QtMultimedia and the several hundred megabytes of the Addons wheel. Speed (`atempo`) and volume
(`volume`) are ffmpeg filters, and changing either restarts the pipeline at the same position;
the volume slider applies 150 ms after it stops moving, so a drag is one restart. Above 100% an
`alimiter` (limit 0.97, no make-up gain) follows the gain: five minutes of a quiet meeting
(mean -31 dB) at 400% had 70,908 samples at full scale without it and none with it, and starting
the pipeline took 0.07 s either way. The volume is a viewing preference like the selection, kept
per recording and per set in `~/.local/state/echo/ui.json` (`volumes`), never in `meta.json`. A second launch forwards
its files to the running window over a local socket. Closing the window while recording leaves a
tray icon; the recording continues.

The look ("Lagoon") lives in `src/echo_app/ui/theme.py`: color tokens for light and dark, the
palette, one stylesheet, icons tinted at paint time and the wave painter. Custom-drawn widgets
read the current tokens when they paint, so switching appearance is live. Icons (Lucide) and the
interface typeface (Manrope) are bundled so Echo looks the same on any desktop; transcripts use
the desktop's own text face.

### Linked sets

A set is one row in the list model (a flat list with heading, recording, set and part rows,
rather than a tree view restyled for one level of nesting). Selecting it gives the transcript
panel and the player a set instead of a recording.

The transcript panel shows a set in the same editor as a recording, laid out as fixed lines (each
part's heading, a status line for a part without text, a blank line between parts) around each
part's editable text. A part map turns document positions into (part, position) and times into
set time, so find, follow-along, passage times, flags, dictionary underlines and playing the
passage at the cursor work unchanged. Three layers keep an edit from landing in the wrong
recording: the editor refuses keys, pastes and menu actions whose range is not inside one part's
text; a check after every change undoes one that reached a heading anyway (an input method); and
saving refuses to split a document whose headings changed. Each part's text is saved only when
it differs from what was loaded, through the same edited-text file as a single recording.

The player plays a set on one timeline: each part's cropped span, end to end. One ffmpeg decode
runs per part, and the next part starts when one ends; measured through PipeWire on this machine,
a hand-over adds about 0.15 s, which falls in the pause between voice notes. The waveform joins
each part's cached peaks, so a set needs no extra decoding. Crop and markers belong to a part and
are edited on it.

After an import, WhatsApp notes are checked for bursts: desktop exports carry the time in the
name (a note starting within 10 minutes of the previous one's end continues it), Android exports
a running number per day (the next number, or up to two further, continues it). The window
offers a run in a banner and never links one on its own.

### System-wide shortcuts

Ctrl+Alt+R and Ctrl+Alt+N are bound through the XDG desktop portal's GlobalShortcuts interface
(KDE Plasma 6, GNOME 46+), which shows its own confirmation dialog once. A portal session lives as
long as the D-Bus connection that created it, so a thread in the window keeps one connection open
and turns the portal's Activated signals into Qt signals. QtDBus aborts inside libdbus when asked
to build the portal's `a(sa{sv})` argument, so this uses `jeepney`, a small pure-Python D-Bus
library. Without a portal, the same actions are CLI commands to bind in the desktop's settings.

## Packaging and dependency risk

| Thing | Where |
|---|---|
| CPython 3.14 | downloaded by uv (`python-preference = "only-managed"`); the system Python is never used |
| Packages | `<clone>/.venv`, from `uv.lock` with sha256 hashes, wheels only (`no-build = true`) |
| `sounddevice` (base) | PortAudio audio where PipeWire does not run the sound: Windows, macOS, PulseAudio-only Linux. Its Windows and macOS wheels carry PortAudio; on Linux it uses the system's `libportaudio` and is only loaded when needed. Brings `cffi`. |
| `onnxruntime` (transcription profiles) | Runs the 27 MB speaker-embedding model on the processor in every profile; torch could not load the ONNX export without a converter. Brings `flatbuffers` and `protobuf`. |
| `jeepney` (base, Linux) | D-Bus for the global-shortcuts portal; QtDBus cannot marshal its argument types. Pure Python, no dependencies. |
| `send2trash` (base) | The desktop trash on Windows and macOS; Linux keeps Echo's own freedesktop code. Pure Python. |
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
- **Speaker turns inside a passage.** Splitting passages where the voice changes, before
  recognition, would label quick exchanges exactly.
