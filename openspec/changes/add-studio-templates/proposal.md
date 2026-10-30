# Templates per meeting type

## Why

One set of sections does not fit every meeting: a one-on-one wants agreements and feedback, an
interview the answers per question, a class the concepts and the homework.

## What Changes

- A template replaces the prompt's guidance on sections; every other rule stays.
- Built-in templates in Spanish: `uno-a-uno`, `entrevista`, `clase`, `cliente`. The user's own are
  Markdown files in `~/.config/echo/studio/templates/NAME.md` and win over a built-in of the same
  name.
- A recording's template is its tag in the category `template` (`template:entrevista`). The arrow
  beside Summarize picks one and summarizes again; `summarize --template NAME` does the same.
- `summary.json` records the template; changing it marks the summary out of date.

## Capabilities

### Modified Capabilities

- `studio-summaries`

## Impact

`src/echo_studio/templates.py` (new), `summary.py`, `ui.py`, `cli.py`, `tests/test_studio.py`,
`docs/guide.md`.
