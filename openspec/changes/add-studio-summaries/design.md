# Design

## Context

The prompt and the choice of one request come from a comparison outside this repository: four
ways of summarizing ten Spanish meetings of 17,000 to 41,000 characters, scored by a second
model against reference summaries. One request with an explicit structure and length target
scored best (mean 0.61); metadata extraction first, a self-critique pass and classifying first
scored 0.56 to 0.58 and made summaries 20 to 50% longer. Every approach invented a summary for a
recording that was mostly unrelated audio. Generation settings moved the score by about 0.01,
less than the 0.03 the same configuration varied between runs, so none is taken from it. None
of its recordings or outputs are in this repository.

## Decisions

- **Settings of its own.** `$XDG_CONFIG_HOME/echo/studio.toml` (`llm_url`, `llm_model`), so
  Echo's `settings.toml` has no Studio keys and removing Studio leaves it as it was. Summaries
  are on when both are set.
- **Key.** `ECHO_LLM_API_KEY`, else the desktop's keyring (see Decisions). None for local
  servers that need none; sent as `Authorization: Bearer` (`x-api-key` to Anthropic); never
  logged.
- **Local or remote.** Local is `localhost`, `*.local`, loopback, private and link-local
  addresses. A remote host gets the warning under the address; summarizing is always a user
  action, so there is no dialog per request.
- **Protocol.** `POST {llm_url}/chat/completions` with model, a system and a user message,
  temperature 0.3, `max_tokens` 2048, timeout 300 s; the reply is the first choice's content,
  with a leading `<think>…</think>` block removed. A 400 naming `max_tokens` (providers that only
  take `max_completion_tokens`) is retried once without it. The comparison's tighter cap (1024)
  is not used: summaries ran about 4,000 characters, close to it, and a cap of 256 halved the
  score; the length is asked for in the prompt instead.
- **Prompt.** `summary.PROMPT`: four to seven `#` sections by topic, bullets at most two deep,
  a last "Próximos pasos"/"Next steps" section with each action in bold and its owner, names,
  numbers, dates and decisions verbatim, about 5 to 10% of the transcript's length, in the
  recording's language. Added to the comparison's prompt: the rule for mostly unrelated audio,
  and that lines start with "Name:" at speaker changes (the text sent is
  `export.with_speakers` when there are speakers). The user message starts with title, date,
  the context line and named people.
- **Long transcripts.** Up to 60,000 characters go in one request. Longer ones are cut between
  paragraphs into parts of at most 40,000 (inside a paragraph, at a sentence end, only when one
  paragraph is longer), each summarized with "part N of M", then one request merges the part
  summaries under the same rules.
- **summary.json** in the recording folder, written atomically and never creating the folder:
  `version`, `text`, `created`, `model`, `server` (host only), `language`, `source_sha256` (of the
  text sent). A different hash of the current text is "the transcript changed since this
  summary". Summarizing again replaces the file; a failed request leaves it as it was.
- **Window.** `attach_window` adds the Summary view when a server is set; the Settings page adds
  it on OK if it was not there, so no restart is needed. The view is read-only Markdown
  (`QTextBrowser.setMarkdown`); the request runs through `run_task`, and selecting another
  recording meanwhile is fine (the result is shown when that recording is selected again).
- **Command line.** Exit codes follow `transcribe`: 0 done, 1 a recording failed, 2 usage, 3 no
  server set up. `--json` prints `info --json`'s dict with a `summary` key (path, created, stale,
  text).

## Decisions made while implementing

- **Sets** show "Select one recording of the set to see or write its summary." Summarizing a set
  as one text is left for later; parts are summarized one by one.
- **Library notes only.** The summary goes into notes exported to a folder (and kept in sync),
  through `markdown_sections`. `export --format md` and `transcribe --format md` stay the
  transcript alone, which is what scripts asking for a transcript expect; the view's Copy gives
  the summary.
- **The window title stays "Echo".** Echo's window rewrites its title every second (recording
  time), so an extension cannot rename it; not worth an extension point.
- **No auto-summarize.** `MainWindow.transcribed` makes it a few lines; it waits until summaries
  are in daily use, since with a cloud server it would send every recording.
- **End to end** with `bin/echo-app` against a local fake server in a scratch data folder: not
  set up exits 3 with the setup text, `--print` printed the summary, a second run sent nothing,
  doctor showed the server line, `ECHO_NO_EXTENSIONS=1 echo-app --help` has no `summarize`.
- **The key in the keyring, not a file** (asked for by the user, who trusted a loose 0600 file
  less than a `.env`). `keychain.py` stores it through `secret-tool`, the Secret Service client
  that libsecret ships, which KDE Wallet and GNOME Keyring both serve: encrypted with the login,
  on standard input so it never shows in `ps`, one entry per server host. No new dependency: the
  `keyring` package would do the same through D-Bus and is not worth a lock entry. Without
  `secret-tool` the key field is off and says to set `ECHO_LLM_API_KEY`; there is no file
  fallback. A key found in the old `llm.key` is moved into the keyring and the file deleted.
  The key is read once per run, so a locked wallet asks once. Tests use a fake `secret-tool`
  (`ECHO_NO_KEYRING=1` keeps every other test away from the real wallet).
- **Anthropic spoken natively.** Anthropic's API is not OpenAI's (`x-api-key`, a required
  `anthropic-version`, `system` apart, content blocks). Its OpenAI-compatible layer is meant for
  trying models, so for `api.anthropic.com` `llm.py` calls `/v1/messages` directly: no
  temperature (current models refuse sampling settings), `max_tokens` 16,000 because thinking,
  always on in current models, counts against it, and on the models that take it
  `fallbacks: "default"` so a declined request is answered by another model in the same call.
  `refusal` and `max_tokens` stops are errors, so a partial summary is never saved.

## Task 1.8 so far

- 2026-10-30, Anthropic: one call of 40 minutes (two tracks), in one
  request. The user read it against the meeting and found nothing invented or missing; the only
  errors were names the transcription had misspelled, which the summary repeats. Still to do:
  four more recordings, one over 60,000 characters (the split-and-merge path), and a local server.
