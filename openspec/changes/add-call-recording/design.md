# Design

## Context

A recording has one source today. The supervisor starts one capture per take (`pw-record` into
`takes/take-NNN.raw`), fsyncs it every 2 s, restarts it after a death or a stall, and on stop
encodes all takes into one verified FLAC. A "Computer audio" source is an output's monitor,
captured with `stream.capture.sink=true`. Reading a source or a monitor in PipeWire does not take
it from anyone: the call app keeps the microphone and its output, and each reader gets its own
copy. Everything after the recorder (playback, waveform, transcription, speakers, export) reads
`audio.flac`; the waveform and the worker decode it to mono with `-ac 1`, playback to stereo.

## Goals / Non-Goals

**Goals:** record the microphone and the computer audio together, with the same no-loss
guarantees for each; keep the two sides apart in the file, since they cannot be separated later;
everything downstream treats the recording as one conversation.

**Non-Goals:** echo cancellation, a choice of output other than the default, more than two
tracks, computer audio on PortAudio.

## Decisions

### Two capture processes, not one combined stream

The microphone and the computer audio are captured by two `pw-record` processes, each writing
its own raw file. A single process would need a virtual node that combines both (a null sink
with links, or a loopback module), owned by some client: if that client dies the node goes with
it, and the links have to be rebuilt after every device change. Two plain captures keep every
existing guarantee as it is, per process: SIGINT flushes, a SIGKILL loses at most 4 KB, a
capture outlives its supervisor and is adopted.

### Takes come in pairs

Each take is a pair: `take-NNN.raw` (the input) and `out-NNN.raw` (the computer audio), started
together and stopped together. If either dies or stalls, both end and a new pair starts, and the
gap is noted once. Restarting only the one that failed would leave the other's take running
across the gap, and aligning the two would then need timestamps the raw files do not carry. A
pair is aligned by construction: both started within moments of each other and both stopped by
the same SIGINT. `take-*.raw` stays the input alone, so elapsed time, markers and the meter keep
reading what they read now.

If the computer-audio capture cannot start (no output at all), the input records alone with a
warning and a note: the input is the half that must not be lost. The next pair tries again.

### Alignment

Measured on the development machine, two `pw-record` processes on one output, started back to
back as the supervisor starts them, with a click played after 0.5 s (five runs): the click
landed at the same sample in both files three times and one 512-frame quantum (10.7 ms) apart
twice, and in every run the difference in file length was exactly that offset: SIGINT stops both
in the same quantum. Across devices the start can differ much more: with the USB microphone, a
webcam microphone, the USB output's monitor and the HDMI output's monitor started together, the
webcam's capture began 299 ms after the others (its device was suspended and had to wake).

There is no drift to correct. Over 300 s, measured after the first 30 s, all four captures
grew by exactly the same number of samples (47,998.27 per second each, 36 ppm below the
system clock): PipeWire runs every stream on one graph clock and resamples each device into it.
So whatever separates the two tracks is fixed when the captures start.

That decides how a pair is aligned. A pair the supervisor stopped together (pause, stop, or a
restart it initiated with both still running) is aligned at its end: the shorter take gets
silence at its start, which is exact to the quantum whatever the startup delays were. A pair
where one capture died or stalled first, or that a crash left behind, has no common end, so it
is aligned at its start (silence at the end of the shorter), off by at most the startup delay.
The supervisor writes `"align": "end"` in the take entry when it stops both together; anything
else is aligned at the start.

### One two-channel FLAC

The pairs are interleaved into one FLAC with two channels: the input on channel 1, the computer
audio on channel 2, each mono. One file keeps crop, export, hashing and the "original is never
altered" rule exactly as they are; two files would need all of them taught about a second file.
The verification is unchanged: the hash of the interleaved stream fed to the encoder must match
the hash of the decoded file. Interleaving is done in Python with `array` slices, in chunks, so
the finalize stays stdlib-only.

`meta.json` gets `channels: 2` and `tracks: ["mic", "computer"]`. A recording without `tracks`
is one source, however many channels it has (an imported stereo file is not a call).

### Mixing: a sum, each side at its level

Downstream, a two-track recording is mixed by summing the channels (`pan=mono|c0=c0+c1`), not
averaging them: ffmpeg's `-ac 1` averages, which would play and transcribe each side 6 dB below
how it was recorded, and speech detection was tuned on single-track levels. The two sides rarely
peak at the same moment; where they do, playback's limiter (already there for the volume boost)
catches it. The waveform and the worker use the same sum.

### Speakers per track

The channels say who is where, so speaker labels use them: each passage goes to the track that
is louder over it (RMS), and passages are clustered within each track. A voice on the
microphone and a voice in the call are never merged, which the embedding alone could do with
similar voices; the microphone's speakers come first, so the user is speaker 1. This assumes
headphones (see "Decisions made while implementing").

### The default output, followed

The computer audio is the default output's monitor, captured with no `--target`, so WirePlumber
links it to the current default output and moves it when the default changes (headphones plugged
in mid-call). Offering every output would add a second picker for a case the desktop's own sound
settings already cover.

### The setting and the command line

The toggle is a setting (`computer_audio`), like the remembered source, and the CLI follows it
unless `--computer-audio` or `--no-computer-audio` is given, so the record shortcut and the
window record the same thing.

## Decisions made while implementing

- **Headphones are assumed.** The user records calls with headphones, so the microphone hears
  only the room. Attributing a passage to the louder track relies on that; behavior with
  speakers was not measured and is not a goal. The README tells the user to wear headphones.
- **Padding, never trimming.** When the input is the shorter take of a pair, it gets the
  silence, and `tracks.time_map` moves markers and gap notes by it, so no captured sample of
  either track is dropped.
- **A pair with one half alive after a crash** is stopped and a new pair started, rather than
  carrying on with one track until the next pause.
- **An empty input take with a non-empty computer-audio take** keeps the latter; finalize builds
  pairs by take number from the files on disk, and a missing half is silence. Take numbers skip
  any number used by either half.
- **Loudness per passage** is measured on the two channels decoded at 4 kHz (57 MB for an hour
  instead of 230 MB at 16 kHz).
- **The command line follows the window's choice** unless `--computer-audio` or
  `--no-computer-audio` is given; the remembered choice is dropped silently where it cannot
  apply (a monitor source, PortAudio), while the explicit flag is an error there. Quick notes
  always record the input alone.
- **Playback of a call always goes through the limiter,** not only above 100% volume, since the
  sum of two sides can exceed full scale.
- **The toggle is a checkable button** under the gain slider, with the second meter beside it
  while it is on; it is disabled while recording.

