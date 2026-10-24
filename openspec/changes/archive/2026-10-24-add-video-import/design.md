# Design

## Context

`importer.import_file` probes a file with ffprobe, copies it to `<data>/.import/` while hashing,
re-reads the copy to verify the hash, and renames it into a new recording folder as
`audio.<ext>`. Duplicates are found by the hash of the audio file (`meta.sha256`). `.mp4` and
`.webm` are in `AUDIO_EXTENSIONS`, so a screen recording is imported today as the whole video
file. `ffmpeg.probe` selects audio streams only and reads the first one.

Measured on a 40-minute OBS meeting (H.264 + AAC 48 kHz stereo 192 kb/s, 1.0 GB, files cached):
sha256 of the video 0.7 s; `ffmpeg -map 0:a:0 -c copy` to `.m4a` 0.3 s, 57 MB; the packet
hashes (`-f streamhash -hash sha256`) of the source track and the `.m4a` are identical, 0.7 s for
both; the `.m4a` reports the same duration as the source track (2374.72 s). Every OBS recording
in the author's videos folder has exactly one AAC stereo track.

## Goals and non-goals

Goals: drop a meeting video and get a recording, with no question asked; keep full quality
whenever the source allows it; the same guarantees as an audio import (nothing partial,
verified, duplicates found). Non-goals: storing or showing the video, a format setting, track
selection in the UI.

## Decisions

### What counts as a video

ffprobe is asked for all streams. A file is a video when it has at least one video stream whose
`disposition.attached_pic` is 0. Cover art in `.m4a`, `.mp3` and `.flac` files is an attached
picture, so music and podcast files stay plain audio imports, copied byte for byte as now. The
extension is only used to find candidate files in folders; the decision is made on the streams,
so an audio-only `.mp4` is still imported unchanged.

### Which audio track

The audio stream marked `disposition.default`, else the first audio stream. OBS's track 1, the
default, is the mix of every source; the other tracks are optional per-source stems, so taking
them all or mixing them would duplicate voices. A video with no audio stream is rejected with
"this video has no sound".

### The format: copy when possible, never ask

| Source codec | Stored as | How |
|---|---|---|
| `aac` | `audio.m4a` | stream copy, `-movflags +faststart` |
| `opus` | `audio.opus` | stream copy into Ogg |
| `mp3` | `audio.mp3` | stream copy |
| `vorbis` | `audio.ogg` | stream copy |
| `flac` | `audio.flac` | stream copy |
| `pcm_*` | `audio.flac` | encode, lossless |
| anything else (`ac3`, `eac3`, `alac`, `wmav2`, …) | `audio.opus` | encode, 128 kb/s, channels kept |

Copying keeps every bit the recorder produced and takes a second; there is nothing to gain by
re-encoding a lossy track. PCM is lossless, so it stays lossless and lands in the same format as
Echo's own recordings. For the rest, Opus at 128 kb/s is transparent for speech, plays in
`pw-play` and PortAudio through ffmpeg like every other format, and is far smaller than FLAC.
All of these are formats the importer and the transcriber already read.

### Verification

- **Copied tracks:** `ffmpeg -i X -map 0:a:N -c copy -f streamhash -hash sha256 -` on the source
  track and on the extracted file; the hashes must match. This proves the packets are the
  source's, which a byte comparison cannot do across containers.
- **Encoded tracks:** the result is decoded in full (as `_duration` already does for files without
  a header duration) and its length must be within 0.5 s of the source track's.
- Then the extracted file's sha256 is computed and stored as `meta.sha256`, as for any import.

A mismatch rejects the file with "could not extract the sound (verification failed)" and leaves
no recording.

### Storage and duplicates

`meta.json` gains one optional object; everything else (`audio`, `sha256`, `duration`,
`source`) means what it means today:

```json
"extracted_from": {"name": "2026-09-23 15-02-29.mp4", "sha256": "…", "size": 1002593404,
                   "track": 1, "method": "copy"}
```

`method` is `copy` or `encode`. `library_hashes` maps both `sha256` and
`extracted_from.sha256` to the recording, so a video dropped again is a duplicate before any
extraction runs, and so is the extracted audio file if someone drops that. The video is hashed
first, in one read (0.7 s for 1 GB), and the duplicate check runs before ffmpeg starts.

### Atomicity

ffmpeg writes to `<data>/.import/<token>.<ext>.partial`; after verification it is renamed into
the new recording folder exactly like a copied file. A crash at any point leaves at most a
staging file, which `clean_staging` already removes at the next import.

### Progress

Extraction runs ffmpeg with `-progress pipe:1` and reports `out_time` against the track's
duration. `import_paths`'s progress callback gains an optional fraction within the current file;
the window's progress dialog shows it, so a long encode (the rare non-copy case) does not look
stuck. Copying is too fast to need it, but goes through the same path.

### Names

OBS's default file name pattern `%CCYY-%MM-%DD %hh-%mm-%ss` (`2026-09-23 15-02-29.mp4`) gives
the date and the title "Screen recording 2026-09-23 15:02". Other names keep today's rule
(underscores to spaces, file time as the date).

### Extensions

`AUDIO_EXTENSIONS` stays as is (it still includes `.mp4` and `.webm`, which can be either) and a
`VIDEO_EXTENSIONS` set is added: `.mkv .mov .m4v .avi .flv .ts .mts .wmv`. `importer.EXTENSIONS`
is their union and is what folder searches, `watch.py` and the file dialog use.

## Risks

- **Variable frame rate or broken timestamps** in a screen recording could make a copied track's
  container duration differ from its content. The streamhash check covers the packets; the
  duration stored is the probed one of the extracted file, which is what the transcriber and
  the player see.
- **Fragmented MP4 still being written** by OBS in a watched folder: the existing "unchanged for
  3 seconds" rule applies, and a probe failure is reported once and retried when the file
  changes.

## Decisions made while implementing

- **Copies fall back to comparing decoded samples.** The packet hash cannot match when the
  container reframes the packets: AAC in MPEG-TS carries ADTS headers that `.m4a` drops, so the
  packet hashes of a correct copy differ. When they differ, the decoded samples of the source
  track and of the result are hashed (`-f hash`) and must match; only if both differ is the file
  rejected. Measured: 1.2 s per side for the 40-minute meeting, versus 0.35 s for packets.
- **More than two channels are mixed down to stereo when encoding to Opus.** libopus refuses
  some surround layouts (5.1(side) from AC-3), and speech gains nothing from them. Copies keep
  their channels.
- **Muxers are named explicitly** (`ipod` for `.m4a`, `opus`, `mp3`, `ogg`, `flac`) and the
  source's metadata is dropped (`-map_metadata -1`), so the extracted file does not carry the
  video's encoder tags or chapter list.
- **`.webm` with Vorbis** was replaced by `.mkv` in the tests: WebM only takes VP8/VP9/AV1
  video, which the test card cannot use with the encoders every ffmpeg build has.
- **OBS names only for video extensions.** A `.flac` named like an OBS recording keeps the plain
  rule, since only a video can be a screen recording.
- **`import_paths` progress** keeps its `(i, n, path)` call before each file and adds a fourth
  argument, the fraction, while a video's sound is extracted. Both callers (the window and
  `echo-app import`) accept it; the watcher calls `import_file` without progress.
