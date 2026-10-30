# Design

## Decisions

- **One module, `ui/motion.py`.** `enabled()` says whether to animate: not when
  `settings.reduce_motion` is on, not when the desktop has animations off (GNOME:
  `gsettings get org.gnome.desktop.interface enable-animations` is `false`; KDE:
  `AnimationDurationFactor=0` under `[KDE]` in `~/.config/kdeglobals`), not when
  `ECHO_REDUCE_MOTION=1` (tests and screenshots). The desktop is asked once per run, the
  `gsettings` call with a one-second limit. Helpers: `fade(widget, to, ms)` (a
  `QGraphicsOpacityEffect` animated and removed at the end, so text renders sharply at rest),
  `slide_width(widget, to, ms)` (animating `maximumWidth`), and `Clock`, a shared 30 Hz timer
  that runs only while some widget asked for frames and the window is shown.
- **Qt animation, no new dependency.** `QPropertyAnimation` and `QVariantAnimation` with
  `OutCubic` (`OutBack` for the marker's bounce). With motion off, every helper jumps straight
  to its end state, so behavior and tests are the same either way.
- **Pulse and blink are painted.** `PulseDot` draws the dot and an expanding ring from the
  clock's time (1.6 s period) instead of animating a property; paused, it blinks with a 1.6 s
  sine. A dot in the stylesheet could not pulse.
- **What does not move.** Hover elevation on buttons from the canvas has no equivalent in Qt
  stylesheets (no transforms or transitions) and is left out rather than faked. The waveform's
  played bars already change color as playback moves.
- **New rows.** The model records when a recording first appears after the first load; the
  delegate draws such a row offset and faded for 320 ms; the list asks the clock for frames only
  while one is young or a transcription runs (the sweep).
- **Smooth follow.** When following playback moves to a passage outside the view, the
  scroll bar is animated to it in 240 ms instead of jumping; a passage already in view does not
  scroll.
