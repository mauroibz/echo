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

## Decisions made while implementing

- **Common-word list**: the first 5,000 lines of FrequencyWords' `es_50k.txt` (OpenSubtitles
  2018), counts removed, in `src/echo_app/data/es_common.txt`. Its content license is CC BY-SA
  4.0, stated in `es_common.LICENSE.txt` next to it and in the README credits.
- **Candidate detection** groups adjacent changed words separated only by spaces into one
  replacement ("lucia fernandes" → "Lucía Fernández") and treats case-only changes inside an
  otherwise equal run ("surus" → "Surus") as replacements too. A title's first word counts only
  as part of a longer name, and a common first word ("Charla Surus") is dropped from the run.
- **A known name corrected from a new spelling** ("Villamil" → "Villaamil" when the entry has
  only "villalmil") adds that spelling as an alias without a chip, with a status-bar message
  saying so; it is visible and removable in Settings → Dictionary. Found in the end-to-end
  check: without it, the corrections made after the first one were lost.
- **Context budget** is counted as characters / 3, a conservative tokens estimate that needs
  no tokenizer in the window process.
- **The canonical spelling corrects its own case variants** ("surus" → "Surus") unless it is a
  single common word.
- **Settings → Dictionary** is a tab of the Settings dialog; its edits are saved with Save,
  like the other settings. Kind for imported lines follows the same two-capitals rule.
- **The status line** of the editor shows "N names corrected" when the corrector changed the
  shown text.
- **Smoke test (1.3)**: ten names do not reduce the word count. With ten names the model still
  wrote "Zurus" on the test clip while two names fix it, so spelling is not asserted there.
- **End-to-end check (4.3)**, real model on the GPU, three LibriVox chapters (Galdós, "Miau"):
  with an empty dictionary chapter 1 spelled the character "Villaamil" as villalmil (3),
  Villalmil (2) and Villa-al-Mil (1). Correcting the first occurrence as the editor saves it
  produced the candidate Villaamil with alias villalmil; accepting it corrected 5 of the 6
  occurrences in chapter 1 without re-transcribing (Villa-al-Mil is another spelling the user
  would correct next). Chapter 2, transcribed with "Términos: Villaamil." in the context, spelled
  it right 4 times out of 4; chapter 3 got 2 of 6 right ("Villamil" 4 times), which the new-alias
  rule above then fixes once the user corrects one. The chip itself was exercised in the
  offscreen UI tests, not by clicking in the window.
