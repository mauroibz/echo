# Tasks

## 1. Playback

- [x] 1.1 `Playback.volume` and `set_volume` (restart at the same position while playing), `volume=` then `alimiter` above 1.0 in the filter chain; `SetPlayback.set_volume`; tests on the ffmpeg command and that a boosted decode of a loud tone has no sample at full scale

## 2. Window

- [x] 2.1 Volume slider (0–400%, label that resets to 100% when clicked, applied 150 ms after the slider settles) next to the speed; enabled with the play button
- [x] 2.2 Per-recording and per-set volumes in `ui.json` under `volumes`; offscreen tests: set, switch, switch back, restart the window

## 3. Docs

- [x] 3.1 README (player controls), `docs/design.md` (playback section, with the limiter measurement), CHANGELOG
