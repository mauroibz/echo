# Echo Studio roadmap

Echo Studio is the optional extension in `src/echo_studio/` that adds features which need a
language model. This file is its plan. `docs/roadmap.md` stays the plan for Echo itself. Each
item below becomes an OpenSpec change in `openspec/changes/` when it starts. The `studio` branch
is Studio's development branch until Studio ships.

## Where Studio stands

Version 1 is implemented on the `studio` branch (2026-10-30): summaries from any OpenAI-compatible
server or Anthropic's API, made as soon as a transcript is ready; built around the user's notes
and markers; templates per meeting type; titles for unnamed recordings; action items; follow-up
drafts; questions about a recording or the whole library, with citations that play the audio.
The API key is in the desktop's keyring.

Version 2 is implemented too (2026-10-31, S10 to S15 below): a home for the next meeting and the
minutes, the calendar read from private ICS addresses, meetings recorded when they start, action
items polished instead of checked off, people by email with their part in each meeting, and the
minutes and items on the command line. Echo's base gained what they needed and shipped on `main`
(`add-background-and-email`, `add-speaker-names-hook`).

After first use on real meetings (2026-11-01, S16): the home became the Briefing, with the week's
meetings and a record switch each; action items gained a description and a note and a column of
their own; people's pages gained stars, tags and points on each person's part. Questions (S6, S7)
were withdrawn until there is a concrete use case for them.

Task 1.8 of `add-studio-summaries` is still open: it checks summaries against the user's own
recordings. The changes stay open until it is done, since they all build on the base summary.

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

### S6 Ask a recording (`add-studio-ask`), withdrawn

Built, then removed after first use (`refine-studio-after-first-use`): it worked in principle but
not well enough in practice. It returns with a concrete use case and stronger retrieval
(embeddings, search). What follows is the plan as it was.


A question box in the Summary view answers from that recording's transcript, with the speakers'
names. Each answer cites the times it draws on, and clicking a time plays the audio there. The
conversation is kept only while the recording is shown. It also works from the CLI:
`echo-app ask ID "question"`.

- New capability `studio-ask`.
- Echo base: a public `MainWindow.show_recording(rid, at=None)` that selects a recording and
  seeks to a time, so an extension can send the user to a passage. Today seeking is internal
  to the player (`ui/player.py`).

### S7 Ask the library (`add-studio-ask-library`), withdrawn with S6

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

## Version 2: a companion to the calendar

Decided with the user on 2026-10-31, after trying version 1. Studio is a side app: it reads the
calendar the user already keeps, records the meetings in it, and turns them into minutes whose
action items can be polished before they go to the team's own tracker (Plane, Trello or
Jira). It does not replace those tools, and it does not try to know more than the
user gives it:

- **No proactive nudges.** Studio shows what the calendar and the recordings say. It does not
  suggest catch-ups, does not say what is "still open on your side", and does not read other
  knowledge sources.
- **Action items are informative.** They can be edited, given context, added and discarded
  before they leave, but Studio does not track whether they got done. No done flags, no "late",
  no Pending screen.
- **Nothing is pushed anywhere yet.** The data leaves through the CLI (`--json`), read by
  whatever the user runs: a cron sync, an agent with a skill, a future importer. A direct export
  to a tracker may come later as its own change.
- **No reminders, no MCP server** for now.

### S10 Editable action items (`change-studio-action-edits`)

Action items lose the done flag, the late dates and the Pending screen. In the minutes each item
can be edited (text, owner, due date), given a line of context, discarded (and restored) and
added by hand. Summarizing again keeps the user's edits, context and discards for items that
still match, and keeps the items the user added.

- Modifies `studio-actions`.

### S11 Calendar (`add-studio-calendar`)

Studio reads one or more private ICS URLs (Google Calendar, Outlook/Teams), kept in the keyring
since they are secrets. From the event happening when a recording started it takes the title
(for an automatic title), the attendees with their emails (offered as speaker names), the
description (as context for the summary) and the video link. Recurring events are expanded by
Studio's own small RRULE reader (stdlib only).

- New capability `studio-calendar`.

### S12 Recording the meetings in the calendar (`add-studio-auto-record`)

When an event with a video link starts and Echo is running, Studio starts a recording titled
after it, and stops it 10 minutes after the event ends unless the user already did. The home
says before that it will record and offers Skip. Echo can start minimized at login so this
works without opening it.

- New capability `studio-auto-record`.
- Echo base: a public start/stop of a recording for an extension, and a "start at login,
  minimized" setting (an autostart entry).

### S13 People by email (`add-studio-people`)

A person gains an email, the key that matches them to calendar attendees. Studio's person page
shows their meetings with an excerpt of each minute and a line on their part in it (from one
extra short request per summary that returns every participant's part), the action items
assigned to them (informative), and the notes.

- New capability `studio-people`.
- Echo base: `email` in the person's profile and a lookup by email; People shows it.

### S14 Studio's home (`add-studio-home`)

With Studio on, the window gets a rail (Home, now Briefing; Recordings, People, Record) and Lagoon's
boldest styling: a deep hero band ending in a wave, large type, minutes as a timeline. Home shows
the next meeting from the calendar (time, title, description, attendees, join link, whether it
will record) and the minutes of past meetings; while a meeting records it shows the timer, the
notes and who was invited. A meeting opens on its minutes and action items, with Transcript and
Ask beside them. Recordings is Echo's window as it is today.

- New capability `studio-home`.
- Echo base: whatever `window_class` cannot reach today; listed at the start of the change and
  shipped as an Echo release first.

### S16 After first use (`refine-studio-after-first-use`)

What a week of real meetings showed:
- **Briefing.** The home is renamed Briefing, with "Coming up": the next 7 days with a record
  switch per meeting.
- **Minutes cards** show the items and notes at a glance.
- **Action items** carry a description (what exactly and why) and a private note, sit in a column
  beside the summary, and are polished on a person's page too.
- **People.** Their part has points; meetings can be starred, tagged and filtered.
- **Ask** is withdrawn.

### S17 Hand-off to a tracker (`add-studio-tracker-handoff`)

The user marks a meeting's polished items ready. Whatever sends them (an agent, a script) lists
them with `echo-app actions --ready` and reports back with `echo-app item … --sent REF` or
`--failed`. Sent items show their link and are frozen. A meeting is processed when everything in
it is sent, so the call can be archived. Echo talks to no tracker.

### S18 Record everywhere, items in a view (`refine-studio-record-and-actions`)

After a few days of use: Record heads the rail (waveform, clock) and the Briefing's hero, so
recording never needs the list of past meetings. Action items get their own view beside Minutes,
each with a done checkbox (the user's mark; still no late dates or reminders) and a To tracker
switch, off by default: sending is opt-in per item, and Mark reviewed replaces Ready to send.

### S15 Data out (`add-studio-cli-data`)

`echo-app meetings --since DATE --json`, `minutes ID --json` (summary, event, attendees, action
items with owner emails, quotes and times) and `actions ID --json`, plus a skill in `agents/`
that tells an agent how to read them.

- Extends `studio-summaries` and `studio-actions` on the CLI.

## Not planned now

- **Proactive briefs and catch-up suggestions,** and anything that needs knowledge beyond the
  calendar and the recordings.
- **Reminders, late dates and a pending list.** The tracker the team uses does that; done is only
  the user's own check mark (S18).
- **Connectors that push** (Plane, Trello, Jira, Slack, Notion, SMTP). The CLI and the ready /
  sent hand-off (S17) are the way out; the team's own agent or script does the sending.
- **An MCP server.** The CLI and an agent skill cover it.

## Never planned

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
| v2a | S10 action edits, S15 data out | Small, and they settle what an item is before anything reads it. |
| v2b | S13 people by email, S11 calendar | Attendees match people by email, so the email comes first. |
| v2c | S12 auto-record, S14 home | Both need the calendar; the home shows all of it. |
| v2d | S16 after first use | What testing the window on real meetings asked for. |
| v2e | S17 hand-off to a tracker | Needs S16's polished items; the last piece of call → tracker. |
| v2f | S18 record everywhere, items in a view | What a few days of use asked for. |

| Phase | Change | Status (2026-11-01) |
|---|---|---|
| 0 | `add-studio-summaries` | done; 1.8 on real recordings is open |
| 1 | `add-studio-notes-first` | done; archives after `add-studio-summaries` |
| 1 | `add-studio-templates` | done; archives after `add-studio-summaries` |
| 1 | `add-studio-auto` | done; archives after `add-studio-summaries` |
| 2 | `add-studio-window` | replaced by Echo's `add_screen` (`add-extension-screens`, archived) |
| 3 | `add-studio-actions` | done; archives after `add-studio-summaries` |
| 3 | `add-studio-follow-up` | done; archives after `add-studio-summaries` |
| 3 | `add-studio-ask` | withdrawn by `refine-studio-after-first-use`; folder removed |
| 4 | `add-studio-ask-library` | withdrawn with `add-studio-ask` |
| 4 | `add-studio-install` | done but the release: merging `studio` into `main` waits for the user |
| v2a | `change-studio-action-edits` | done; archives after `add-studio-actions` |
| v2a | `add-studio-cli-data` | done; archives with the other Studio changes |
| v2b | `add-studio-people` | done; archives with the other Studio changes |
| v2b | `add-studio-calendar` | done; archives with the other Studio changes |
| v2c | `add-studio-auto-record` | done; archives with the other Studio changes |
| v2c | `add-studio-home` | done; archives with the other Studio changes |
| v2d | `refine-studio-after-first-use` | done; archives with the other Studio changes |
| v2e | `add-studio-tracker-handoff` | done; archives with the other Studio changes |
| v2f | `refine-studio-record-and-actions` | done; archives with the other Studio changes |
