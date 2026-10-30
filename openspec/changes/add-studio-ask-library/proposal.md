# Ask the library

## Why

"What did we agree with Acme about prices in October?" spans recordings. Echo's search finds the
recordings; an answer needs the passages.

## What Changes

- An Ask screen (button beside People, Ctrl+Shift+A) takes questions across recordings. A first
  short request turns the question into up to four searches (words, `@people`, `#tags`); Echo's
  index finds the matching passages (`Index.passages`); only those, numbered, go to the model,
  which cites them as [n]. A citation opens the recording at its passage.
- `echo-app ask "question"` prints the answer and the passages it cites.

## Capabilities

### Modified Capabilities

- `studio-ask`

## Impact

`src/echo_studio/ask.py` (`searches`, `find_passages`, `ask_library`, `link_refs`), `ask_ui.py`
(`AskScreen`), `cli.py`; `tests/test_studio.py`; `docs/guide.md`. Uses `Index.passages`
(`add-extension-screens`).
