# Design

## Context

`worker/asr.py` places text in the decoder's context slot; `build_context(extra)` puts the
caller's sentence before the fixed style sentence (terms after the style sentence returned
nothing on one clip). `worker/service.py` reads `context` from `transcribe.requested`, passes
it to the engine, keys the partial-results cache on it and writes it into `transcript.json`.
The engine retries a passage that comes back implausibly short with the style sentence only
and then with no context, keeping the fullest result, so a bad context sentence cannot
silently drop speech. This change adds no evaluation tooling; that retry is the safety net.

## Goals / Non-Goals

**Goals:** names and terms spelled right with no setup; the dictionary grows from correcting
and titling; every automatic change visible and undoable; model output stays immutable.

**Non-Goals:** grammar or style correction; correcting common words; a personal adapter
(later change); any dialog in the normal flow.

## Decisions

### Store

`glossary.toml`:

```toml
[[people]]
name = "Lucía Fernández"
aliases = ["Lucia Fernandez", "Lucía"]
used = "2026-10-24T10:00:00+02:00"

[[terms]]
name = "Surus"
aliases = ["surus", "Zurus"]
used = "2026-10-20T18:12:00+02:00"

muted = ["Cosa"]
```

`dictionary.py` loads, saves atomically (same `fsutil` helpers as settings), and exposes
`entries()`, `add(kind, name, aliases)`, `remove`, `merge`, `mute`, `touch(name)`.

### Candidates from edits

On autosave of `transcript.edited.txt`, diff model text and edited text with
`difflib.SequenceMatcher` on word tokens. A `replace` opcode whose edited side is one to three
tokens and (a) starts with a capital letter not at sentence start, or (b) has been seen as the
same replacement in another recording (a small `~/.local/state/echo/candidates.json` counts
them) becomes a candidate with the model-side tokens as the alias. Already-known names, muted
words and pure case or accent changes of common words (checked against a 5,000-word Spanish
frequency list bundled as a text file) are skipped. Titles: capitalized tokens in a renamed
title that are not in the first sentence of the transcript are candidates of kind `people` if
they look like names (two capitalized tokens) else `terms`.

### The chip

`TranscriptPanel` shows at most one chip at a time under the editor: "Add *Surus* to the
dictionary · Not this word". It appears after the save that produced it and disappears on the
next recording change or after the user acts. No animation, no stacking: the next candidate
waits for the next save.

### Context sentence

`dictionary.context_sentence(extra_line, budget_tokens=120)`:
"Personas: A, B. Términos: C, D." with people before terms, each group most recently `used`
first, cut at the budget by whole entries. The recording's line goes first, verbatim, then this
sentence. The result is stored in `transcribe.requested` as `context`, so the worker is
unchanged. Each queued job calls `touch` on the entries it included.

### Corrector

`dictionary.correct(text, segments) -> (text, edits)` replaces whole-token matches of aliases
(case-insensitive, accent-insensitive via the index's fold) with the canonical name, and
multi-token names whose fuzzy ratio against a same-length window is 0.9 or better. The result
is written to `transcript.corrected.json` (text, segment texts, and the list of
`{segment, start, end, before, after}`), never to `transcript.json`. The editor shows
`corrected` when there is no edited text, underlines each edit, and offers "Undo this
correction" in the context menu, which rewrites `corrected.json` without that edit and adds
the pair to a per-recording `rejected` list so it is not reapplied. When the dictionary
changes, the panel re-runs the corrector for the visible recording and the library runs it
lazily for others on open. Corrections are applied before the edited text exists; once the
user has edited, the corrector is not run on their text.

### Settings page

A list with name, kind, aliases, last used; Remove and Merge buttons; Import from a text file
(one name per line). Same visual language as the existing Settings dialog.

## Risks

- Over-eager candidates annoy. The chip is one at a time, mutes are permanent, common words
  are filtered; if that is still noisy, raise the "seen twice" rule to three.
- Context budget. Long dictionaries push old entries out of the sentence; the corrector still
  catches their aliases.
