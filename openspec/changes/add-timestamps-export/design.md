# Design

## Context

`segment_spans()` maps model segments to character spans of the model text, and the panel
clears the spans once the user has edited (`_spans = []` when `rec.is_edited()`), so nothing
today can say which passage an edited sentence belongs to. Both the margin and the exports
need that mapping for edited text.

## Decisions

- **Alignment of edited text to segments.** `transcript.align(model_segments, edited_text)
  -> list[(start_char, end_char, seg_index)]` in a new stdlib module
  `src/echo_app/align.py`: tokenize both texts into words with positions, run
  `difflib.SequenceMatcher(autojunk=False)` on folded words, and carry each model segment's
  first word to its matched edited word; a segment whose first word was deleted starts at the
  next matched word; the last segment runs to the end. Result cached per
  (edited mtime, transcript mtime). The panel uses it for follow-along too, which fixes the
  existing gap where edited transcripts do not highlight.
- **Margin.** `Editor` gets a `TimestampMargin` widget set as its left viewport margin (same
  technique as Qt's line-number example): for each segment span whose first line is visible,
  draw `m:ss` (or `h:mm:ss` past an hour) in the dim text color, right-aligned, only on the
  first line of a passage, and only when paragraph or passage starts change. Toggle: View →
  "Passage times" (`Ctrl+T`), setting `show_timestamps: bool = False`.
- **Copy with timestamps.** Edit → "Copy with timestamps" (`Ctrl+Alt+C`): one line per
  passage, `[m:ss] text`, paragraph breaks kept as blank lines.
- **Formats.** In `export.py`: `to_srt(cues)`, `to_vtt(cues)`, `to_json(rec, cues)` where
  `cues = [(start, end, text)]` from the alignment on the current text. SRT: `HH:MM:SS,mmm`,
  cues numbered from 1, blank line between. VTT: `WEBVTT` header, `HH:MM:SS.mmm`. JSON:
  `{"id", "title", "created", "duration", "language", "edited": bool, "segments": [{"start",
  "end", "text", "paragraph", "speaker"?}]}` with two-decimal times. The export dialog offers
  all five formats by extension; `export_transcript` dispatches on suffix.
- **CLI.** `echo-app export ID [--format txt|md|srt|vtt|json] [--out PATH]`, default format
  from the suffix of `--out`, else `txt` to stdout.
