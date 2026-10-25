# Proposal

## Why

Meetings recorded from the screen are often much quieter than a voice note: a 40-minute
reference meeting averages -31 dB, about 11 dB below ordinary speech, so even with the system
volume at its maximum it is hard to follow. Echo plays audio at its recorded level and has no
way to raise it.

## What Changes

- **A volume slider in the player**, from 0% to 400%, next to the speed. Above 100% it boosts
  the sound; a limiter keeps loud moments (laughter, a knock on the microphone) from clipping.
- **Remembered per recording.** A quiet meeting stays boosted the next time it is opened, and
  the next recording plays at its own level (100% unless it was changed). A linked set has one
  volume for all its parts.
- Clicking the percentage puts it back to 100%.

Playback only: the audio file, exports and transcription are unchanged.

Out of scope: automatic loudness normalization, a volume for exported audio.

## Capabilities

### Modified Capabilities
- `playback-and-crop`: Playback gains a volume.
- `desktop-app`: Layout persists also restores each recording's volume.

## Impact

`audio/playback.py` (a volume and limiter in the ffmpeg filter chain, `set_volume` on
`Playback` and `SetPlayback`); `ui/player.py` (the slider, per-recording volumes);
`ui/main_window.py` (saving them in `ui.json`); `README.md`, `docs/design.md`. No new
dependencies.
