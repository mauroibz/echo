# Proposal

## Why

Much of the audio worth transcribing is recorded elsewhere: WhatsApp voice notes, phone
recordings, meeting exports. Echo needs to take these in by drag and drop or from the command
line, without altering them and without creating duplicates.

## What Changes

- Import audio files and folders into the library, by drag and drop or `echo-app import`.
- Accept every common audio format ffmpeg can decode, including all WhatsApp voice-note
  variants (Ogg Opus `.opus`/`.ogg`, `.m4a`, `.aac`, `.amr`), MP3, WAV, FLAC, WebM, WMA, AIFF.
- Keep the original file byte-identical inside the recording folder, verified by hash.
- Recognize WhatsApp file names and use their date and time for the title and sort order.
- Skip files already in the library (same content), and report files that are not audio.
- Optionally queue transcription automatically after recording or import (on by default when
  transcription is installed).

## Capabilities

### New Capabilities
- `audio-import`: accepting external audio files into the library.

### Modified Capabilities

## Impact

New module `src/echo_app/importer.py`, CLI command `import`, one new setting
(`auto_transcribe`). Uses ffprobe.
