## Why

Echo used the desktop's default widgets and icons, which made it look like a utility rather than
a finished app, and its look changed from machine to machine. The owner chose the "Lagoon"
direction from three mockups and asked for a stronger, opinionated identity.

## What Changes

- A bundled theme, Lagoon: a deep teal sidebar with a light canvas and white cards, coral for
  recording, aqua as the accent, and waves as the motif. Light is the default; dark and
  "match the system" are in Settings and switch live.
- The recorder gets a wordmark, a coral record pill, a large tabular timer and waves that swell
  with the input level and turn coral while recording. They rest when nothing is heard.
- Library rows show status pills only for states that need attention; the waveform draws as
  rounded aqua bars; empty states get glyphs; the welcome screen gets a banner.
- Icons (Lucide, ISC) and the interface typeface (Manrope, OFL) ship with the app, tinted and
  rendered by Echo, so the app looks the same on any desktop. The app icon is redrawn to match.
- Input names drop PipeWire's channel-layout suffix in the picker ("Analog Stereo").

## Impact

- New `ui/theme.py` and `ui/assets/`; every UI module takes colors from the theme.
- New setting `theme` (light, dark, system).
