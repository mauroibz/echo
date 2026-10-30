# Titles from the summary

## Why

A recording nobody named is titled with its first sentence ("Bueno, empezamos"), which says
nothing in the list. Once there is a summary, a short title can say what the meeting was about.

## What Changes

- After a summary is written, a recording whose title is still automatic gets a title of at most
  8 words from a short second request over the summary. A title the user typed is never touched.
- A setting on the Summaries page, on by default: "Give recordings you did not name a short title
  from their summary". The CLI follows it too.

(Summaries when a transcript is ready, the other half of this item in the roadmap, went into
`add-studio-summaries` at the user's request.)

## Capabilities

### Modified Capabilities

- `studio-summaries`

## Impact

`src/echo_studio/summary.py` (`retitle`), `jobs.py`, `cli.py`, `config.py`, `ui.py`,
`tests/test_studio.py`, `docs/guide.md`.
