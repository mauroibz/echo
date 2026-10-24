# Proposal

## Why

The model misspells names and domain terms, and it does so consistently: "Zurus" for "Surus",
a friend's name as a common word. The worker already accepts a per-job context string and
putting known terms in it has been shown to fix their spelling, but nothing feeds that string.
Users correct the same words by hand in every transcript, and that work is thrown away.

## What Changes

- A **dictionary** of people and terms (`~/.config/echo/glossary.toml`, plain text) with a
  canonical spelling and aliases per entry.
- It grows from work the user already does. On saving an edit, Echo compares the edited text
  with the model text; a replaced capitalized word, or a word replaced the same way twice
  across the library, becomes a candidate shown as a small chip under the editor ("Add Surus
  to the dictionary"). One click adds it and records the model's spelling as an alias.
  Dismissing mutes that word. Capitalized words typed into titles are candidates too. There is
  no dialog and no form.
- An optional line under the title, "Who is speaking, what about", used as extra context for
  that recording only.
- Every transcription request builds a context sentence from the dictionary (most recently
  used first, within a token budget) and the recording's line, and stores it in the request;
  the worker and provenance already handle the rest. `echo-app transcribe --context` for the CLI.
- A corrector applies aliases to the finished model transcript on a copy, underlining each
  replacement in the editor with one-click undo. A new alias is applied to existing transcripts
  at once, without re-transcribing.
- Settings → Dictionary lists entries for removal or merging. It is for repair, not entry.

## Capabilities

### New Capabilities
- `dictionary`: known people and terms, how they are learned and how they are applied.

### Modified Capabilities
- `transcription`: context from the dictionary, provenance of the context used.
- `transcript-editor`: candidate chip, underlined corrections, per-recording context line.

## Impact

New `src/echo_app/dictionary.py` (store, candidate detection, corrector; stdlib only), changes
in `transcription.py`, `cli_tr.py`, `ui/transcript.py`, `ui/player.py` (title area),
`ui/dialogs.py` (settings page), `library.py` (context line in `meta.json`,
`transcript.corrected.json`), one new case in `tests/test_model_smoke.py`. The UI process
still never imports torch.
