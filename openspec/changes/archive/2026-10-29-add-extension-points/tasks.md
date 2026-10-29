# Tasks

- [x] 1.1 `extensions.py`: `KNOWN`, `loaded()` (skips on `ECHO_NO_EXTENSIONS`, logs import failures), `call(hook, *args)` collecting results and logging failures; `conftest.py` sets `ECHO_NO_EXTENSIONS`; tests with a fake extension in a temporary folder, including one that raises on import
- [x] 1.2 Non-Qt hooks: `register_cli` in `cli.py`, `doctor_checks` in `doctor.run_all`, `markdown_sections` in `export.to_markdown`; tests
- [x] 1.3 Window: `_build` split into `_build_parts` and `_build_layout`, splitter sizes into `_restore_layout`/`_save_layout`; `window_class` in `ui/app.py`; `attach_window`; the existing UI tests pass unchanged
- [x] 1.4 `add_view` with the switch over the transcript and `show_subject` calls; `settings_pages` with `apply()`; `transcribed` signal; offscreen tests for each, and that a window without extensions has no switch
- [x] 1.5 Isolation test: no core module imports an extension or a network library outside `models.py`
- [x] 1.6 `docs/design.md` (Extensions section, principle), `docs/roadmap.md` (summaries move to Echo Studio), `CHANGELOG.md`
