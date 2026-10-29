# Proposal

## Why

Echo stays a local recorder and transcriber. Features that need a language model or a cloud
service (summaries first) are to be built as a separate package, Echo Studio, that installs
into the same app: one install, one window, one data folder. For that, Echo needs a few places
where such a package can add to it, and a guarantee that Echo without it is the same as today
and talks to no server.

## What Changes

- Echo looks for optional extension packages next to `echo_app` (the first is `echo_studio`)
  and loads the ones present. An extension that fails to load is logged and skipped; Echo
  starts without it. `ECHO_NO_EXTENSIONS=1` starts without any.
- An extension can add command-line subcommands, setup checks to `echo-app doctor`, sections to
  Markdown notes, pages to Settings, views next to the transcript, and replace the main window
  with a subclass that lays the same parts out differently.
- The main window's construction is split into making and connecting its parts (the recorder,
  search, list, player, transcript) and laying them out, so a subclass can lay them out its own
  way without copying the wiring.
- The window emits a signal when a recording's transcript is written, for extensions that act on
  new transcripts.
- A test keeps the core from importing any extension and from opening network connections
  outside the model download.

Nothing changes for a user without an extension.

## Capabilities

### New Capabilities
- `extensions`: how optional packages add to Echo, and what Echo guarantees without them.

## Impact

New `src/echo_app/extensions.py`; `cli.py` (extension subcommands), `doctor.py`, `export.py`
(`to_markdown`), `ui/app.py` (window class), `ui/main_window.py` (parts and layout, views,
`transcribed` signal), `ui/dialogs.py` (Settings pages); `tests/conftest.py` (no extensions by
default); new `tests/test_extensions.py`. No new dependency.
