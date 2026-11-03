## Why

A 3-person call came out as 7 speakers after two manual merges (9 before them); the user names
the same people again and again. Measured on the user's 10 latest calls: clustering is per track,
and without headphones each voice reaches both tracks, so almost everyone appeared twice, plus
fragments of a few seconds. Known voices were already reliable (the right person best in 28 of 28
named speakers) but only suggested at 0.85 and never named. The name field could only be typed.

## What Changes

- After labeling, speakers are joined as merges: the same known person, the same voice across
  tracks (0.82), and fragments under 1.5% of the speech. Never two speakers the user named apart.
  Older recordings are grouped once, when opened.
- Suggestions from 0.75 with a 0.1 lead, from the voices as they are now; a voice learned from two
  recordings names the speaker itself at 0.85 with a 0.2 lead, without teaching the voice.
- A second speaker given a name already used in the recording joins the first.
- A dropdown beside the name field: invitees, the closest voices, everyone known.

## Capabilities

### Modified Capabilities

- `transcript-editor`

## Impact

New `src/echo_app/speaker_groups.py` (stdlib); `worker/service.py`, `library.py` (two meta
fields), `ui/transcript.py`, `ui/transcript_speakers.py`; `tests/test_speaker_groups.py`,
`tests/test_speaker_merge.py`; `docs/guide.md`, `docs/design.md`. No new dependency.
