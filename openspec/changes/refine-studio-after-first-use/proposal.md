## Why

The first real use of Studio's window, on a week of meetings, showed what does not work yet:

- The home showed the next meeting but not the rest of the week, and skipping a meeting was
  only possible for the next one.
- A minutes card said "6 action items" without showing any, so the home was not a glance.
- After "Summarize again" the action items were laid out at no height: the header and Add showed,
  the items did not.
- Items had a title and nothing more; whoever picks one up in the tracker needs to know what
  exactly and why. Under the summary they were squeezed below the text.
- On a person's page the items were read-only, and their meetings could not be marked or sorted
  out, so the list did not help.
- Ask worked in principle but not well enough in practice. It returns later, with a concrete use
  case and better retrieval (embeddings, search).

## What Changes

- **Briefing.** Home is renamed Briefing. Beside the minutes, "Coming up" lists the meetings of
  the next 7 days by day, each with a switch for whether it is recorded when it starts. A meeting
  without a video link can be switched on.
- **Minutes cards.** Each card shows the gist, up to three action items with owner and date (and
  how many more), the user's notes, the people, the tags and a star.
- **Action items.**
  - Each item has a description written with it: what exactly, why, and the details said.
  - The user can add a private note beside the context.
  - The items get a column of their own beside the summary.
  - They can be polished on a person's page too.
  - The list's height bug is fixed.
- **People.**
  - Each person's part has points: what they reported, proposed, asked, objected to or took on.
  - Meetings can be starred and tagged, and filtered by All, Starred or a tag.
- **Command line.**
  - Items carry `description` and `note`; meetings carry `starred`.
  - `echo-app meetings --starred` lists only the starred meetings.
  - The text output prints the description and context, never the note.
- **BREAKING** (unreleased): Ask is removed: its views, page and `echo-app ask`. The
  `add-studio-ask` and `add-studio-ask-library` changes are withdrawn.

## Impact

- Code: `src/echo_studio/home.py`, `actions.py`, `actions_ui.py`, `ui.py`, `parts.py`,
  `people_ui.py`, `meetings.py`, `marks.py` (new), `data.py`, `cli.py`, `widgets.py`,
  `__init__.py`, `window.py`; `ask.py` and `ask_ui.py` removed. Echo gains `star` and
  `star-filled` icons (Lucide).
- Files:
  - `actions.json` items gain `description` and `note`.
  - `parts.json` goes to version 2, with `{part, points}` per person; version 1 is still read.
  - `marks.json` is new.
  - The meetings state file gains `wanted`.
- No new dependency.
