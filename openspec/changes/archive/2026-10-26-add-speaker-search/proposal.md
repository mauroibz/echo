# Proposal

## Why

Once speakers have names, the questions change: which meetings was Ana in, and what did she say
about the price. Search today finds words anywhere in a transcript, so "precio" brings every
meeting where anyone said it, and there is no way to ask for a person.

## What Changes

- **`@Ana` in the search** lists the recordings where a speaker named Ana talks (any word of the
  name: `@ana` finds "Ana López"; `@ana_lopez` asks for the whole name). Several `@` must all
  speak.
- **`@Ana precio`** finds only what Ana said: the words must be in her passages. Each result
  shows a line under its title with her matching words ("Ana: …el precio sube en enero…"), and
  opening it finds the words in her passages only, starting at the first.
- Typing `@` in the search offers the names of the people who speak in your recordings.
- The same queries work in `echo-app list`.

Only named speakers can be searched; "Speaker 2" is not a person yet.

## Capabilities

### Modified Capabilities
- `desktop-app`: searching by speaker, snippets and finding within a speaker's passages.
- `command-line`: `@name` in `list`.

## Impact

`index.py` (a `spoken` full-text table of each named speaker's text, a `speakers` table, query
parsing, snippets), `ui/library_view.py` (a third line with the snippet), `ui/main_window.py`
(completion, carrying the speaker to the transcript), `ui/transcript.py` (finding within a
speaker's passages), `README.md`, `docs/design.md`, `CHANGELOG.md`. No new dependencies.
