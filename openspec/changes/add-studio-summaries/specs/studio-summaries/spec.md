## ADDED Requirements

### Requirement: Off until a server is set
Summaries SHALL be off until a server address and model name are saved. Until then the window
SHALL show no summary view, `echo-app doctor` SHALL not check a server, and `echo-app summarize`
SHALL say how to set one up and exit with code 3.

#### Scenario: Studio installed, nothing set up
- **WHEN** Echo starts with Studio present and no server set
- **THEN** the window has no Transcript/Summary switch, and Settings has a Summaries tab

#### Scenario: Setting it up
- **WHEN** the user enters an address and model in Settings, Summaries, and presses OK
- **THEN** the Summary view appears beside the transcript without a restart

### Requirement: Any OpenAI-compatible server or Anthropic, key kept private
Studio SHALL summarize through the chat completions endpoint of an OpenAI-compatible server,
local or remote, and through Anthropic's Messages API when the address is Anthropic's. An API
key SHALL be read from `ECHO_LLM_API_KEY` or the desktop's keyring, one per server, and SHALL
never be written to a file, a settings file or the log. Settings SHALL name a remote
host in a warning that transcripts are sent to it.

#### Scenario: Remote server
- **WHEN** the address is `https://api.example.com/v1` and a key is entered
- **THEN** Settings shows "Transcripts you summarize are sent to api.example.com.", the key is in the keyring, and no file in Echo's configuration folder contains it

#### Scenario: Anthropic
- **WHEN** the address is `https://api.anthropic.com/v1`, with a key and a model
- **THEN** summaries are requested from `/v1/messages` with the key in `x-api-key` and an
  `anthropic-version` header, and a declined or cut-off answer is reported as an error

#### Scenario: Local server without a key
- **WHEN** the address is `http://127.0.0.1:8080/v1` and no key is set
- **THEN** no warning is shown and requests carry no Authorization header

### Requirement: Summarize a recording
The user SHALL be able to summarize a transcribed recording from the Summary view. The summary
SHALL be organized by topic with a last section of next steps, in the recording's language,
saved as `summary.json` in the recording's folder with the server's host, the model and a hash
of the text it was made from. A failed request SHALL keep an earlier summary.

#### Scenario: Summarize
- **WHEN** the user selects a transcribed recording, opens Summary and presses Summarize
- **THEN** "Summarizing…" shows, then the summary, and `summary.json` is in the recording's folder

#### Scenario: Edited after
- **WHEN** the transcript is edited after the summary was made
- **THEN** the view says the transcript changed since the summary and offers Summarize again

#### Scenario: Server refuses
- **WHEN** the server answers 401
- **THEN** the error is shown with the server's message and the earlier summary is unchanged

### Requirement: Long transcripts in parts
A transcript over 60,000 characters SHALL be sent in parts of at most 40,000 characters cut
between paragraphs, and the part summaries merged by one more request into one summary.

#### Scenario: Two-hour meeting
- **WHEN** a transcript of 130,000 characters is summarized
- **THEN** the server receives one request per part and one merge request, and one summary is saved

### Requirement: Summaries from the command line and in notes
`echo-app summarize ID...` SHALL summarize recordings, skip those whose summary is current
unless `--force`, print with `--print`, report with `--json`, and exit 0, 1, 2 or 3. Library
notes SHALL carry a recording's summary under "Resumen" (or "Summary") before the transcript.

#### Scenario: Repeat
- **WHEN** `echo-app summarize ID` runs twice with no change to the transcript
- **THEN** the second run sends no request and exits 0

#### Scenario: Note
- **WHEN** a summarized recording is exported to a notes folder
- **THEN** its note has a "Resumen" section with the summary, headings demoted, above the transcript

### Requirement: Server check
With a server set, `echo-app doctor` SHALL report whether it answers and whether it lists the
configured model.

#### Scenario: Wrong model
- **WHEN** the model is not among the names the server lists
- **THEN** doctor warns and shows the names it has
