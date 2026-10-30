# Echo Studio roadmap

Echo Studio is the optional extension in `src/echo_studio/` that adds features which need a
language model. This file is its plan. `docs/roadmap.md` stays the plan for Echo itself. Each
item below becomes an OpenSpec change in `openspec/changes/` when it starts. The `studio` branch
is Studio's development branch until Studio ships.

## Where Studio stands

`add-studio-summaries` gives Studio:

- a server setting (any OpenAI-compatible URL or Anthropic's, a model and a key in the keyring);
- `echo-app summarize` with `--force`, `--print` and `--json`;
- a Summary view next to the transcript;
- a summary section in Markdown export;
- a doctor check for the server.

The summary is one request for transcripts up to 60,000 characters. Longer ones are split into
parts and merged. The result goes to `summary.json` with the hash of its source, so a summary
of an edited transcript shows as out of date.

Task 1.8 of that change is still open. It checks summaries against five of the user's own
recordings. Every item below except the window and distribution changes gets its result from a
prompt, so 1.8 comes first: if the base summary is wrong on real transcripts, every later item
gets the same error.

Studio has two rules, which follow from Echo's principles:

- **Echo without a server is unchanged.** Every Studio feature appears only once a server is
  set. Nothing runs against a remote server without the user starting it or turning it on.
- **Studio's results are files in the recording folder,** next to the transcript, and carry the
  hash of what they were made from. The index may cache them; it never holds the only copy.

## Version 1

### S1 Summaries guided by the user's notes (`add-studio-notes-first`)

A recording's `notes` and its markers' notes are what the user thought mattered while it
happened. They go into the request ahead of the transcript, as the summary's skeleton: each note
must be covered, expanded from what was said around it (for a marker, the passage at its time).
The rest of the transcript fills in around them. A recording with neither summarizes as now.

- Modifies `studio-summaries`. The source hash covers notes and markers too, so editing a note
  marks the summary out of date.
- Echo base: none. `notes` and `markers` are already in `meta.json`.

### S2 Templates per meeting type (`add-studio-templates`)

A template is a plain text file that replaces the section guidance in the prompt: a one-on-one
wants agreements and feedback, an interview wants answers per question, a class wants concepts
and assignments. Echo ships a few in Spanish. The user's own templates live in
`~/.config/echo/studio/templates/<name>.md` and win over built-ins with the same name.

The template comes from a tag in the category `template`, for example `template:cliente`. A
recording with no such tag uses the general prompt in use today. The Summary view shows the
template used and offers the others when summarizing again; `summarize --template NAME` does the
same from the CLI.

- Modifies `studio-summaries`. `summary.json` records the template's name and hash.
- Echo base: none. Tag categories already exist (`library.tag_category`).

### S3 Automatic titles (`add-studio-auto`)

Summaries when a transcript is ready were moved into `add-studio-summaries` at the user's
request, on by default. What is left here:

- **Better titles.** On by default once a server is set. A recording whose title is still
  automatic (`title_auto`, today the transcript's first sentence) gets a short title from the
  summary. A title the user typed is never touched.

- Modifies `studio-summaries`, adds requirements to `studio`.
- Echo base: none. The `transcribed` signal and `title_auto` already exist.

### S4 Action items (`add-studio-actions`)

The summary's next steps become data: `actions.json` in the recording folder, one entry per
item with its text, owner (a person's name as Echo knows it, or empty), due date if one was
said, the time in the audio where it came up, and a done flag. They come from a second, short
request over the finished summary. That way the summary prompt stays the one 1.8 measured, and
the first request is not asked for two formats.

The items are shown in three places:

- in the Summary view, as checkboxes;
- in a Pending screen gathering open items across the library, filtered by person and tag;
- in a person's profile, as their open items.

Checking an item writes `actions.json`. Summarizing again keeps the done flags of items that
still match.

- New capability `studio-actions`.
- Depends on S8, which provides the Pending screen.
- Echo base: a hook for sections in the people dialog (`person_sections(name)`), with
  `ui/people.py` showing what extensions return under the notes.

### S5 Follow-up draft (`add-studio-follow-up`)

"Draft follow-up" in the Summary view writes a short email from the summary and the action
items: greeting, what was agreed, who does what and by when. The draft opens in an editable box
with Copy, and with Open in mail, which hands it to the user's mail program through a `mailto:`
link. Studio sends nothing and holds no mail account. It also works from the CLI:
`summarize --follow-up` prints the draft.

- New capability `studio-follow-up`.
- Depends on S4.
- Echo base: none.

### S6 Ask a recording (`add-studio-ask`)

A question box in the Summary view answers from that recording's transcript, with the speakers'
names. Each answer cites the times it draws on, and clicking a time plays the audio there. The
conversation is kept only while the recording is shown. It also works from the CLI:
`echo-app ask ID "question"`.

- New capability `studio-ask`.
- Echo base: a public `MainWindow.show_recording(rid, at=None)` that selects a recording and
  seeks to a time, so an extension can send the user to a passage. Today seeking is internal
  to the player (`ui/player.py`).

### S7 Ask the library (`add-studio-ask-library`)

The Ask screen takes questions across recordings ("what did we agree with Acme about prices in
October?"):

1. Echo's search index picks candidate recordings, narrowed by the people, tags and dates the
   question names. The model turns the question into that search, in a first short request.
2. Only the matching passages, with their recording and time, go to the model to answer.
3. Each citation opens the recording at its passage.

There are no embeddings and no second index. The FTS5 index already covers the text and the
speakers, which keeps Studio within the lean rule. Embeddings come back only if measured
answers miss what plain search finds.

- Extends `studio-ask`.
- Depends on S6 and S8.
- Echo base: a read-only search call that returns passages with recording id and time, for
  extensions (`index.speech_matches` returns recordings, not passages).

### S8 Studio's window (`add-studio-window`)

Once Studio has Pending and Ask, they do not fit as views beside a transcript. Studio
subclasses `MainWindow` through `window_class` and adds a sidebar with Recordings (today's
window, unchanged), Pending and Ask. Without a server the sidebar is hidden and the window is
Echo's, so turning Studio on or off never moves the user's recordings view.

- New capability `studio-window`.
- Comes before S4's Pending screen and S7.
- Echo base: whatever the subclass cannot reach through `_build_parts`/`_build_layout` today.
  The change starts by listing that, and the base part ships as an Echo release first, as
  `add-extension-points` did.

### S9 Installing Studio (`add-studio-install`)

How a user gets Studio:

- `install.sh --studio` installs Echo with Studio's package present.
- `uninstall.sh` removes it.
- `doctor` says whether Studio is installed.

Studio uses only the standard library, so it adds no dependency to `uv.lock`. Until Studio
ships, the branch holds it and is rebased on each Echo tag. After that, the plan is that Studio
lives in the same repository and is versioned with Echo: there is one app and one release, and
the installer decides whether Studio is included.

- New capability `studio-install`; modifies `install` in Echo's specs.
- Echo base: the installer flag and the doctor line.

## Version 2: accounts and connectors

These need an account, a token or a server that Studio does not run, so each one comes with its
own decision about where credentials live. Today the only secret is the model key, in the
desktop's keyring.

### S10 Calendar (`add-studio-calendar`)

Studio matches a recording to the calendar event happening when it started. From the event it
takes:

- the event title, for an automatic title;
- the attendees, offered as speaker names and given to transcription as context;
- the event description, as a line of context for the summary.

The first version reads a private ICS URL: read-only, no OAuth, and it works for Google,
Outlook and Fastmail. A sign-in with Google or Microsoft is a later step.

### S11 Send and publish (`add-studio-connectors`)

Studio sends a summary, its action items or the follow-up to another service:

- email through SMTP with the user's own account;
- a Slack message through an incoming webhook;
- a Notion page through an integration token.

Each connector is a small module with a settings page, a Send action and a record in the
recording folder of what went where. Markdown export already covers Obsidian and similar tools.

### S12 People across meetings (`add-studio-people-brief`)

Before a meeting, a short brief per person: what was talked about with them in the last
meetings, open items both ways, and the notes from their profile. It is built from S4 and S7.

## Not planned

- **Share links and team spaces.** They need a server that holds other people's meetings. That
  is a different product, with hosting, accounts and privacy obligations, and it goes against
  plain files as the truth.
- **A bundled model.** Studio talks to whatever server the user runs or pays for. Shipping
  weights would break the lean install, and the model revisions in `models.py` are for
  transcription only.
- **Live notes during the recording.** Echo transcribes after recording, by design. Streaming
  transcription would be a change to Echo's core, not to Studio.

## Sequencing

| Phase | Changes | Why in this order |
|---|---|---|
| 0 | 1.8 of `add-studio-summaries` | Every later item is a prompt over the base summary. |
| 1 | S1 notes first, S2 templates, S3 titles | They improve the summary that exists, need nothing from Echo base, and are small. |
| 2 | Echo base hooks (`show_recording`, `person_sections`, passage search, what S8 lists); S8 window | One Echo release with the hooks, then the window the next items live in. |
| 3 | S4 actions, S5 follow-up, S6 ask a recording | S5 needs S4's data. S6 needs `show_recording`. |
| 4 | S7 ask the library; S9 install | S7 is the largest. S9 ships Studio as version 1. |
| v2 | S10 calendar, S11 connectors, S12 people brief | Accounts and tokens, decided one service at a time. |

| Phase | Change | Status (2026-10-29) |
|---|---|---|
| 0 | `add-studio-summaries` | done; 1.8 on real recordings is open |
| 1 | `add-studio-notes-first` | done; archives after `add-studio-summaries` |
| 1 | `add-studio-templates` | done; archives after `add-studio-summaries` |
| 1 | `add-studio-auto` | done; archives after `add-studio-summaries` |
| 2 | `add-studio-window` | planned |
| 3 | `add-studio-actions` | planned |
| 3 | `add-studio-follow-up` | planned |
| 3 | `add-studio-ask` | planned |
| 4 | `add-studio-ask-library` | planned |
| 4 | `add-studio-install` | planned |
| v2 | `add-studio-calendar` | planned |
| v2 | `add-studio-connectors` | planned |
| v2 | `add-studio-people-brief` | planned |
