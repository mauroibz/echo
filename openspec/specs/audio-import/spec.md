# audio-import Specification

## Purpose
Brings audio recorded elsewhere into the library unchanged, so it can be played and
transcribed like Echo's own recordings.

## Requirements

### Requirement: Import files and folders
Echo SHALL import audio files given by drag and drop onto the library or by `echo-app import`.
A dropped folder SHALL be searched recursively for audio files. Each imported file SHALL become
one recording.

#### Scenario: Drop several voice notes
- **WHEN** the user drops three WhatsApp voice notes on the library
- **THEN** three recordings appear, each playable, with a progress indication while copying

### Requirement: Supported formats
Echo SHALL accept any file in which ffmpeg finds an audio stream, and SHALL in particular accept
Ogg Opus (`.opus`, `.ogg`), AAC (`.m4a`, `.aac`, `.mp4`), AMR (`.amr`, `.3gp`), MP3, WAV, FLAC,
WebM, WMA and AIFF. A file without an audio stream SHALL be rejected with a message naming the
file and the reason, and the rest of the batch SHALL continue.

#### Scenario: Not an audio file
- **WHEN** the user drops a PDF together with two audio files
- **THEN** the two audio files are imported and the user is told the PDF is not audio

### Requirement: Originals preserved
The imported file SHALL be copied, never moved, and the copy SHALL be verified to be
byte-identical to the source before the recording appears in the library. An interrupted import
SHALL leave no partial recording.

#### Scenario: Import interrupted
- **WHEN** the application is killed in the middle of copying a large file
- **THEN** the library contains no recording for that file and the source file is unchanged

### Requirement: Duplicate detection
Echo SHALL skip a file whose content is identical to an audio file already in the library and
SHALL tell the user which recording it duplicates.

#### Scenario: Same voice note dropped twice
- **WHEN** a voice note that is already in the library is dropped again
- **THEN** no new recording is created and the message names the existing recording

### Requirement: Meaningful titles and dates
The title SHALL be derived from the file name. For WhatsApp file names that include a date
(for example `PTT-20261023-WA0003.opus` or `WhatsApp Audio 2026-10-23 at 14.32.11.opus`),
the recording's date SHALL be taken from the name and the title SHALL read "WhatsApp voice
note" with that date. Otherwise the file's modification time SHALL be the recording's date.

#### Scenario: WhatsApp file name
- **WHEN** `WhatsApp Audio 2026-10-23 at 14.32.11.opus` is imported
- **THEN** the recording is titled "WhatsApp voice note 2026-10-23 14:32" and sorts at that date

### Requirement: Automatic transcription
When transcription is installed and the `auto_transcribe` setting is on (the default),
recordings that finish recording or importing SHALL be queued for transcription automatically.

#### Scenario: Import with auto transcription
- **WHEN** a voice note is imported with transcription installed and the setting on
- **THEN** the recording shows as queued for transcription without further action
