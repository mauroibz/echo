# Design

## Context

Recording folders and the index exist (library-storage spec). WhatsApp on Android exports voice
notes as `PTT-YYYYMMDD-WAnnnn.opus` (Ogg Opus) and shared audio as `AUD-YYYYMMDD-WAnnnn.*`;
WhatsApp Desktop and iOS exports use `WhatsApp Audio YYYY-MM-DD at HH.MM.SS.*`
(sometimes `WhatsApp Ptt ...`). Older Android notes are `.amr`.

## Goals / Non-Goals

**Goals:** stdlib-only importer usable from the CLI and from a UI worker thread.

**Non-Goals:** importing from URLs, unpacking WhatsApp chat export zips, video files' audio
tracks beyond what ffprobe exposes (a video file with an audio stream is accepted as audio).

## Decisions

- **Probe before copy** with ffprobe; reject when no audio stream. Extensions are only used to
  filter folder scans, never to decide what is audio.
- **Copy as `audio.<original extension, lowercased>`** through `audio.<ext>.partial`: stream
  copy with sha256 computed on the way, fsync, re-hash the written file, rename. The recording
  folder and `meta.json` are created only after the audio is in place, so an interrupted import
  leaves at most a stray `.partial` in a hidden staging folder (`<data>/.import/`) that is
  cleaned on the next start.
- **Duplicates** via the sha256 stored in every `meta.json` (recordings store the FLAC hash,
  imports the original file hash). The importer loads the hash set once per batch.
- **Dates**: WhatsApp patterns first, then file mtime. `created` holds that date; the id keeps
  the import time so it stays unique.
- **Duration**: ffprobe duration; when missing (some Opus/AMR streams), decode and count.
- **Auto transcription** writes the `transcribe.requested` marker; the worker change consumes it.
  The setting is honored by both recorder (on finalize, in the UI/CLI that observed the stop)
  and importer.

## Risks / Trade-offs

- [Huge files and slow disks] → copying runs in a background thread in the UI with progress per
  file; CLI prints per-file results.
