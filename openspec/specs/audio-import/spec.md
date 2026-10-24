# audio-import Specification

## Purpose
Brings audio recorded elsewhere into the library unchanged, so it can be played and
transcribed like Echo's own recordings.

## Requirements

### Requirement: Import files and folders
Echo SHALL import audio and video files given by drag and drop onto the library or by
`echo-app import`. A dropped folder SHALL be searched recursively for audio and video files.
Each imported file SHALL become one recording.

#### Scenario: Drop several voice notes
- **WHEN** the user drops three WhatsApp voice notes on the library
- **THEN** three recordings appear, each playable, with a progress indication while copying

#### Scenario: Drop a folder of screen recordings
- **WHEN** the user drops a folder holding two `.mkv` meeting recordings and a `.png`
- **THEN** two recordings appear and the image is ignored

### Requirement: Supported formats
Echo SHALL accept any file in which ffmpeg finds an audio stream, and SHALL in particular accept
Ogg Opus (`.opus`, `.ogg`), AAC (`.m4a`, `.aac`), AMR (`.amr`, `.3gp`), MP3, WAV, FLAC, WebM,
WMA and AIFF audio, and MP4, MKV, MOV, M4V, AVI, FLV, MPEG-TS and WMV video. A file without an
audio stream SHALL be rejected with a message naming the file and the reason, and the rest of
the batch SHALL continue.

#### Scenario: Not an audio file
- **WHEN** the user drops a PDF together with two audio files
- **THEN** the two audio files are imported and the user is told the PDF is not audio

### Requirement: Originals preserved
An imported audio file SHALL be copied, never moved, and the copy SHALL be verified to be
byte-identical to the source before the recording appears in the library. A video file SHALL be
read only, its extracted audio verified as the extraction requirement says. An interrupted
import SHALL leave no partial recording.

#### Scenario: Import interrupted
- **WHEN** the application is killed in the middle of copying a large file
- **THEN** the library contains no recording for that file and the source file is unchanged

### Requirement: Duplicate detection
Echo SHALL skip a file whose content is identical to an audio file already in the library, or to
a video whose audio is already in the library, and SHALL tell the user which recording it
duplicates. For a video this check SHALL run before any extraction.

#### Scenario: Same voice note dropped twice
- **WHEN** a voice note that is already in the library is dropped again
- **THEN** no new recording is created and the message names the existing recording

#### Scenario: Same meeting video dropped twice
- **WHEN** a meeting video that was imported before is dropped again
- **THEN** no new recording is created and the message names the existing recording

### Requirement: Meaningful titles and dates
The title SHALL be derived from the file name. For WhatsApp file names that include a date
(for example `PTT-20261023-WA0003.opus` or `WhatsApp Audio 2026-10-23 at 14.32.11.opus`),
the recording's date SHALL be taken from the name and the title SHALL read "WhatsApp voice
note" with that date. For OBS's default video names (`2026-09-23 15-02-29.mp4`) the date SHALL
be taken from the name and the title SHALL read "Screen recording" with that date and time.
Otherwise the file's modification time SHALL be the recording's date.

#### Scenario: WhatsApp file name
- **WHEN** `WhatsApp Audio 2026-10-23 at 14.32.11.opus` is imported
- **THEN** the recording is titled "WhatsApp voice note 2026-10-23 14:32" and sorts at that date

#### Scenario: OBS file name
- **WHEN** `2026-09-23 15-02-29.mp4` is imported
- **THEN** the recording is titled "Screen recording 2026-09-23 15:02" and sorts at that date

### Requirement: Automatic transcription
When transcription is installed and the `auto_transcribe` setting is on (the default),
recordings that finish recording or importing SHALL be queued for transcription automatically.

#### Scenario: Import with auto transcription
- **WHEN** a voice note is imported with transcription installed and the setting on
- **THEN** the recording shows as queued for transcription without further action

### Requirement: Watched folders
Echo SHALL import new audio files that appear in the user's watched folders while it runs and
on start, once each file has stopped changing, leaving the original in place and skipping
duplicates. Failures SHALL be reported once per file and not retried on every scan.

#### Scenario: Phone sync drops a voice note
- **WHEN** a `.opus` voice note appears in a watched folder
- **THEN** within ten seconds it is in the library with its WhatsApp date and, if enabled, queued for transcription

### Requirement: Bursts of voice notes
Echo SHALL recognize WhatsApp voice notes that form one burst: with desktop-export names, each
starting within 10 minutes after the previous one ends; with Android names, the same date and
consecutive numbers allowing gaps of up to two. Recognition SHALL consider the files of one
import together with the library's recordings from the same day, SHALL skip recordings already
in a set when proposing a new one, and SHALL only produce an offer for the window to show.

#### Scenario: A note that continues a linked set
- **WHEN** a watched folder imports PTT-20261023-WA0007 and WA0004 to WA0006 are already a set
- **THEN** Echo offers to add the new note to that set

### Requirement: Video files import as their audio
Echo SHALL import a file that contains a video stream (not counting attached pictures) by
extracting one audio track into the new recording, and SHALL NOT copy, move or modify the
video. The track SHALL be the one marked default, else the first. The track SHALL be copied
without re-encoding into its matching audio container when its codec is AAC, Opus, MP3, Vorbis
or FLAC; PCM SHALL be stored as FLAC; any other codec SHALL be encoded to Opus at 128 kb/s. The
user SHALL NOT be asked about format or track. A video without an audio stream SHALL be rejected
with a message saying it has no sound.

#### Scenario: An OBS meeting recording
- **WHEN** the user drops a 40-minute OBS `.mp4` with one AAC track on the window
- **THEN** within a few seconds a recording with an `.m4a` of that track appears, the video stays where it was, and transcription starts if enabled

#### Scenario: Screen recording without sound
- **WHEN** a video with no audio stream is imported
- **THEN** no recording is created and the user is told the video has no sound

### Requirement: Extracted audio is verified
A copied track SHALL be verified by comparing the packet hash of the source track with that of
the extracted file or, when the container changes the packets' framing, the hash of the decoded
samples; an encoded track SHALL be decoded in full and its length SHALL be within
0.5 s of the source track's. Extraction SHALL happen in the staging folder so that an
interrupted or failed extraction leaves no recording.

#### Scenario: Killed during extraction
- **WHEN** Echo is killed while extracting the audio of a long video
- **THEN** the library has no recording for it and the next import removes the staging file
