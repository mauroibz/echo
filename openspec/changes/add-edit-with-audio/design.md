# Design

## Context

`Ctrl+,` is Settings and `Ctrl+.` is free; the player can seek and play but has no
"play a span then stop". Passage lookup under the cursor needs the alignment from
`add-timestamps-export` for edited text; that change is a dependency.

## Decisions

- **Shortcuts.** `Ctrl+.` play the passage under the cursor (press again to stop);
  `Ctrl+Alt+.` next passage and play; `Ctrl+Alt+,` previous passage and play;
  `Ctrl+Shift+.` next flagged passage and play (no-op with a status message until
  `add-low-confidence-marking` is archived). All are actions in the Edit menu so they appear
  in the shortcuts dialog.
- **Span playback.** `PlayerPanel.play_span(start, end)` seeks, plays, and stops at `end`
  using the existing tick timer; a `span_finished` signal lets the panel keep the highlight.
- **Auto-pause.** While a span is playing, any key press in the editor pauses playback and
  starts a 1-second single-shot timer; when it fires with no further keys, playback restarts
  from the span start. Setting `edit_autopause: bool = True`, shown in Settings as "Pause
  playback while typing, replay the passage after".
- **Highlight.** The passage being played uses the existing follow-along selection.
