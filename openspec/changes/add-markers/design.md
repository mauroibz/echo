# Design

## Context

`WaveformView` already draws "interruption markers" (capture gaps from `meta.gaps`) as thin
lines and takes a `markers` list; user markers are a second, visually distinct kind. The
supervisor loop runs twice a second and, after `refactor-recorder-portability`, reads a
command file. The recording list and the window both learn about a recording's state through
`status.json` and `meta.json`.

## Decisions

- **Storage.** `meta.json` gains `markers: [{"at": 612.4, "note": "decisión sobre el precio"}]`
  with `at` in seconds of the captured audio (what the user hears on playback), sorted. The
  `Meta` dataclass gets `markers: list[dict] = field(default_factory=list)`.
- **While recording.** The `command` file accepts `mark` and `mark <note>` in addition to
  `pause`, `resume`, `stop`. The supervisor computes `at` as bytes captured so far across all
  takes divided by `rate * channels * 2`, so pauses are excluded and gaps are honored, appends
  to `session.json` `markers`, and `finalize` copies them into `meta.json`. `recover` does the
  same for a crashed recording. Before the refactor lands, do not implement markers.
- **Shortcut.** `M` while recording and the window is focused outside a text field (a
  `QShortcut` on the main window with `WindowShortcut` context, enabled only while
  `recorder_panel.session` is not None), the tray menu item "Add marker", and
  `echo-app mark [--note TEXT]`. After the key, a one-line `QLineEdit` slides in under the
  recorder panel with the placeholder "Note for this marker (Enter to save, Esc to skip)";
  it closes on Enter, Escape, or 10 seconds without typing. The marker is saved immediately
  at key time; the note is attached afterwards by rewriting the last marker through a
  `note` command.
- **Waveform.** User markers are drawn as a small triangle on the top edge in the accent
  color with a hairline down the wave; hovering shows the note as a tooltip; dragging moves
  it (snap to pauses like crop, Shift disables); right-click "Remove marker"; double-click on
  the wave with Ctrl adds one at that position; `Ctrl+M` adds one at the playhead when not
  recording. All edits write `meta.json` through `Recording.update`.
- **Navigation.** `Alt+Right` / `Alt+Left` jump to the next / previous marker and keep
  playing if playing. Shortcuts dialog and README list them.
- **Transcript.** A marker anchors to the passage whose span contains `at` (or the next
  passage); the editor shows a small accent dot in the margin, with the note as tooltip;
  clicking plays from the marker. Rendering reuses the margin introduced by
  `add-timestamps-export`; if that change is not archived yet, draw the dot in the editor's
  left viewport margin directly and let the later change merge the two.
- **CLI.** `echo-app list` shows the marker count; `echo-app markers ID` prints them.
