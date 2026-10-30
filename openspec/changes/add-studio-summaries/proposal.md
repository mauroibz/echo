# Proposal

## Why

A meeting of an hour is fifty thousand characters of transcript; most of the time the user wants
its decisions, open points and who does what next. A language model writes that in under a
minute. It needs a model Echo does not run, so it is Echo Studio's first feature: an extension
installed into the same app (see Extensions in `docs/design.md`), not part of Echo.

## What Changes

- New package `src/echo_studio/`, loaded by Echo's extension points when present.
- Settings gets a "Summaries" tab: the address of an OpenAI-compatible server (local, such as
  llama.cpp, Ollama or vLLM, or a cloud provider) or Anthropic's, a model name and an optional
  API key, kept in the desktop's keyring. A server off this computer and its network is named in a
  warning that transcripts are sent to it. "Test" asks the server for its models.
- Once a server is set, a Summary view sits beside the transcript: Summarize, Summarize again,
  Copy, and a line when the transcript changed since the summary. Without a server the window is
  Echo's, with only the Settings tab added.
- `echo-app summarize ID... [--force] [--print] [--json]`.
- Library notes (export to a folder, and sync) carry the summary under "Resumen".
- `echo-app doctor` checks the server when one is set.

## Capabilities

### New Capabilities
- `studio-summaries`: summaries of a recording's transcript from an OpenAI-compatible server.

## Impact

Only `src/echo_studio/` and `tests/test_studio.py`; Echo's code is unchanged. No new dependency:
`urllib.request` and `json` cover one POST and one GET.
