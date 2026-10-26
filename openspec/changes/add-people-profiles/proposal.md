# Proposal

## Why

Echo now knows people: their names, their voices, which recordings they speak in. None of it can
be seen in one place, and there is nowhere to write who someone is ("Acme's CFO, prefers
mornings"). The person is the natural way into a pile of calls: open Ana, see every call she was
in and what was said.

## What Changes

- **People** (View → People, Ctrl+Shift+P; also "Open profile" on a speaker's name in the
  transcript) lists everyone: people in the dictionary and everyone named as a speaker, with how
  many recordings they speak in. A filter field narrows it.
- **A profile** for each person:
  - **Notes**, free text.
  - **Their recordings**: every recording they speak in, with how long they spoke, newest first;
    double-click opens it.
  - **Voice**: ▶ plays a few seconds of them from their latest recording; "Forget voice" when
    Echo learned it wrong.
  - **Aliases**: other spellings, the same as the dictionary's.
  - **Tags**, such as `client:Acme`. A recording where a person speaks counts as carrying their
    tags in search, so `#client:acme` also finds calls with Acme's people that were not tagged.
- Profiles are plain files in the data folder (`people/<name>.json`), next to the recordings they
  describe, so they move and are backed up with them.
- `echo-app people [--json]` lists people with their recordings, tags and notes.

## Capabilities

### Modified Capabilities
- `desktop-app`: the People window and profiles.
- `library-storage`: profile files; a person's tags in search.
- `command-line`: `echo-app people`.

## Impact

New `people.py` (profile files), `index.py` (person tags in tag search), new `ui/people.py`,
`ui/main_window.py` (menu, opening a recording), `ui/transcript.py` ("Open profile"),
`dictionary.py` (forgetting a voice), `cli.py`, `README.md`, `docs/design.md`, `CHANGELOG.md`. No
new dependencies.
