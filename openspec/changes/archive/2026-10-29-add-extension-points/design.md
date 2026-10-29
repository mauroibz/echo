# Design

## Decisions

- **Discovery by a fixed list.** `extensions.KNOWN = ("echo_studio",)`: a package of that name
  importable from the source tree (`bin/echo-app` puts `src/` on the path) or the environment
  is loaded. Entry points need an installed distribution, and Echo is not installed as one
  (`package = false`). A list of names in one constant is the whole registry; a later extension
  adds its name there.
- **Hooks are optional module attributes.** An extension's top-level module may define any of:
  - `register_cli(subparsers)`: add subcommands, like `cli_ext.REGISTRARS`.
  - `doctor_checks() -> list[doctor.Check]`: appended to `echo-app doctor` and Check setup.
  - `markdown_sections(rec) -> list[tuple[str, str]]`: (heading, Markdown) pairs inserted in a
    recording's note after its header and before its text, as `## heading`.
  - `settings_pages() -> list[tuple[str, QWidget]]`: tabs added to Settings after Import. A
    page's `apply()` is called on OK; raising `ValueError` shows its message and keeps the dialog
    open, like the data-folder check.
  - `window_class() -> type[MainWindow]`: the window to open instead of `MainWindow`; the first
    extension that returns one wins.
  - `attach_window(window)`: called once the window is built, to add menu actions, views and
    connections.
  The non-Qt hooks are called only from the places that already exist for them, so the CLI and
  doctor never import Qt for an extension.
- **Failure is contained.** Importing an extension, and each hook call, is wrapped: an exception
  is logged with its traceback (`extensions` logger) and that extension's hook is skipped.
  Recording, transcription and editing never depend on an extension's code running.
- **Parts and layout.** `MainWindow._build` becomes `_build_parts` (create and connect the
  recorder panel, search, tag bar, burst banner, list, selection bar, player and transcript) and
  `_build_layout` (sidebar, splitters, central widget). `_restore` and `_save_state` keep the
  window's geometry and the player's speed and volumes; the splitter sizes move to
  `_restore_layout` and `_save_layout`, which a subclass overrides with its own layout.
- **Views next to the transcript.** `MainWindow.add_view(title, widget)` puts a switch over the
  transcript card ("Transcript" and each added title). Without added views there is no switch,
  so the window looks as it does now. A view widget may define `show_subject(rec, linked)`,
  called whenever the selection changes or the shown recording or set is refreshed; `rec` is the
  recording, or None when `linked` is a `(LinkedSet, parts)` pair or nothing is selected.
- **`transcribed` signal.** `MainWindow.transcribed(str)` carries the id of a recording whose
  `transcript.json` was written while the window runs (its modification time differs from the
  last one seen). Recordings already transcribed when the window opens do not emit it.
- **Isolation test.** `tests/test_extensions.py` parses every module under `src/echo_app` and
  fails if one imports an extension package, or imports `socket`, `ssl`, `http`,
  `urllib.request`, `requests` or `httpx`. The model download goes through `huggingface_hub`,
  imported only in `models.py`, which the test allows by name. Qt's networking classes are
  allowed only as `QLocalServer`/`QLocalSocket` (the single-instance socket).
- **Tests run without extensions.** `conftest.py` sets `ECHO_NO_EXTENSIONS=1` for every test, so
  a checkout with `src/echo_studio` present still tests Echo alone; extension tests load a fake
  extension from a temporary folder.

## Decisions made while implementing

- **Views also follow file changes**, not only the selection: `show_subject` runs when the list
  model reports that the shown recording's (or set part's) folder changed, the same signal the
  list uses, so a view sees a new transcript without polling. It does not run on the window's
  one-second refresh.
- **A failing window class falls back** to `MainWindow` with the error logged, as a failing hook
  is skipped; an exception in Echo's own window still stops the start as before.
- **`transcribed`** starts from the modification times of the recordings listed when the window
  opens; a folder that appears later with a transcript already in it (a sync from another
  computer) emits it once.
- **Extension subcommands** are registered after Echo's own and through `extensions.call`, so an
  extension cannot replace a core command: argparse rejects the clashing name, the error is
  logged, and `echo-app` works without that extension's commands.
