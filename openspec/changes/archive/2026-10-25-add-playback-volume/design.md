# Design

## Context

`Playback` decodes with ffmpeg (`-af atempo=…` for speed) and pipes 16-bit PCM into the
backend's output (pw-play, or PortAudio). Changing the speed restarts the pipeline at the
current position, which takes about a tenth of a second. The speed is one value for the whole
window, saved in `~/.local/state/echo/ui.json`.

## Decisions

### Gain in the ffmpeg filter chain

The volume is an ffmpeg `volume=` filter after `atempo`, and changing it restarts the pipeline
the way a speed change does. This works the same on every output backend. PipeWire's own
stream volume could change without a restart, but PortAudio has none, and a boost above 1.0 in
PipeWire clips in the same way.

### A limiter above 100%

A gain above 1.0 is followed by `alimiter=limit=0.97:level=false` (`level=false`: no automatic
make-up gain, so 100% stays the recorded level and the slider means what it says). Measured on
the reference meeting (mean -31.2 dB, peaks -5.5 dB), five minutes at 400%: without the limiter
70,908 samples were clipped at full scale; with it the peak is -0.3 dB and none are, while the
mean moves from -19.6 to -20.1 dB. Starting the pipeline takes 0.07 s with or without it. At
100% or less there is no limiter, so normal playback is unchanged.

### Range 0% to 400%

400% is +12 dB, enough to bring the reference meeting to ordinary speech level with room to
spare. Steps of 5% on the slider, 10% with Page Up and Page Down.

### Applied after the slider settles

Each change restarts the pipeline, so a drag applies the value 150 ms after the slider stops
moving instead of on every pixel. The percentage label follows the slider at once.

### Per recording, in ui.json

A boost is a property of one quiet recording, so the volume is remembered per recording (and
per linked set), unlike the speed. It lives in `ui.json` under `volumes`, keyed by recording
or set id, holding only values other than 100%. It is a viewing preference like the selection,
so it stays out of the recording's `meta.json`, which is the library's data.

## Decisions made while implementing

- Double-clicking the slider also resets it to 100%, as the input gain slider in the sidebar
  does; the percentage next to it is a button for the same thing.
- The slider is enabled and disabled with the play button. A linked set's volume applies to
  every part, since the parts play through one `Playback`.
- The value is stored in `volumes` as soon as the slider moves, and only the restart of the
  pipeline waits for it to settle, so a refresh of the same recording during a drag keeps the
  new value.
- The slider got a light-surface style in `theme.py` (accent groove, outlined handle), matching
  the sidebar's gain slider in shape.
