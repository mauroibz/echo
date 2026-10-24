# Proposal

## Why

Transcripts carry passage times but the user never sees them and cannot take them anywhere.
Quoting a moment from an interview, or using a recording as subtitles, needs them.

## What Changes

- A toggle shows passage start times in the editor margin (off by default, remembered).
- "Copy with timestamps" and export to SRT, VTT and JSON (segments with times and text),
  next to the existing TXT and Markdown.
- Exports use the edited text when it exists, mapped back onto segments by the same alignment
  the follow-along highlight already computes.

## Capabilities

### Modified Capabilities
- `transcript-editor`: timestamps in the margin, copy and export with times.

## Impact

`export.py` (SRT, VTT, JSON writers), `ui/transcript.py` (margin, toggle, menu items),
`cli.py` (`echo-app export ID --format srt|vtt|json|txt|md`).
