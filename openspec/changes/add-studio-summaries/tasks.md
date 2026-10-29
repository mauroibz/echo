# Tasks

- [x] 1.1 `config.py`: `studio.toml`, key from the environment or a 0600 file, `is_local`; tests
- [x] 1.2 `llm.py`: chat completion and model list over `urllib`, `<think>` removed, retry without `max_tokens`, errors with the server's message; tests against a fake server (success, 401, unreachable, no key)
- [x] 1.3 `summary.py`: prompt, parts and merge over 60,000 characters, `summary.json` with the source hash, staleness; tests for request content, part sizes and counts, a failed request keeping the file
- [x] 1.4 `cli.py`: `summarize` with `--force`, `--print`, `--json` and exit codes 0/1/2/3; tests
- [x] 1.5 Hooks: `register_cli`, `doctor_checks`, `markdown_sections`, `settings_pages`, `attach_window`; tests
- [x] 1.6 Window: Settings page (remote warning, Test, `apply` validation), Summary view (Summarize, Copy, staleness, progress for parts), added without restart; offscreen tests, and a window without a server unchanged
- [x] 1.7 `docs/guide.md` section on Echo Studio
- [ ] 1.8 Summarize five of the user's own recordings, one over 60,000 characters and one call, with a local server and with a cloud one; read each against its transcript for invented facts, wrong owners and missed decisions; write counts and timings (not content) in `design.md` (needs hardware: real recordings and a running server or a cloud API key)

## Blocked

- **1.8** needs a language-model server and the user's recordings, which an agent does not have
  here (no server was running on this computer). To run it: set a server in Settings,
  Summaries (for a local one, for example `llama-server -m <model.gguf> --port 8080`, then
  `http://127.0.0.1:8080/v1`), select five transcribed recordings including one over an hour and
  one call, press Summarize on each, and compare each summary with its transcript: every
  decision present, owners right, nothing that was not said. Note the time each took.
