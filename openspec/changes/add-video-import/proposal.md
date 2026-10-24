# Proposal

## Why

Meetings are the longest and most valuable recordings, and they are usually captured as screen
recordings (OBS, the desktop's own recorder, a video call's export), not as audio. Echo already
accepts `.mp4` and `.webm` as audio extensions, but it copies the file byte for byte: a
40-minute OBS recording is about 1 GB, of which the audio is 57 MB. Common video containers
(`.mkv`, OBS's old default, and `.mov`) are not recognized at all, and folders and watched folders
skip them.

The person importing a meeting does not care how the audio is taken out of the video, and should
never be asked. Echo should take the audio track, keep it at full quality with no re-encoding
when it can, verify it, and treat the result like any other imported recording.

## What Changes

- **Video files import as their audio.** A file whose streams include a video track (cover art
  in an audio file does not count) is imported by extracting one audio track into the recording
  folder. The video itself is never copied, moved or changed.
- **One rule for the format, no choice offered.** The audio track is copied without re-encoding
  into the matching audio container when one exists (AAC to `.m4a`, Opus to `.opus`, MP3 to
  `.mp3`, Vorbis to `.ogg`, FLAC to `.flac`); uncompressed PCM is stored as FLAC; anything else
  is encoded to Opus at 128 kb/s. For OBS's default AAC this takes under a second for a 40-minute
  meeting and loses nothing.
- **Verified like any import.** A copied track is checked packet for packet against the source;
  an encoded one is decoded in full and its length checked. Extraction happens in the staging
  folder, so an interrupted import leaves nothing behind.
- **Duplicates by the video's hash.** The video's sha256 is kept in `meta.json`, so dropping the
  same video twice names the existing recording instead of importing it again.
- **More extensions:** `.mkv`, `.mov`, `.m4v`, `.avi`, `.flv`, `.ts`, `.mts`, `.wmv` in folder
  searches, watched folders and the file dialog. Pointing a watched folder at OBS's output
  folder imports every meeting by itself.
- **OBS file names give the date.** `2026-09-23 15-02-29.mp4` becomes "Screen recording
  2026-09-23 15:02", dated from the name.
- **The window says it:** the drop overlay reads "Drop audio or video to import", the open
  dialog lists both, and import progress covers the extraction of a long file.

Out of scope: keeping or playing the video, choosing between several audio tracks in the UI,
mixing tracks.

## Capabilities

### Modified Capabilities
- `audio-import`: video files, their audio extraction, verification and duplicates; OBS names.
- `library-storage`: what an imported recording's audio file is when the source was a video.
- `desktop-app`: the drop overlay, the open dialog and progress for video.

## Impact

`audio/ffmpeg.py` (probe reports video streams and every audio track; extract and verify);
`importer.py` (video path, extensions, OBS names, duplicate by source hash); `watch.py` (uses the
importer's extension set, so no change beyond tests); `ui/main_window.py` (overlay text, dialog
filter, per-file progress); `README.md`, `docs/design.md`. No new dependencies: ffmpeg and
ffprobe already do the work.
