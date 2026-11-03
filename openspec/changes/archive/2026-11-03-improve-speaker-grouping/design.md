## Measurements (the user's own calls, centroids and names only, nothing copied)

- Ten latest calls: 2 to 19 speakers labeled. Across tracks, one voice measured 0.84 to 0.96, two
  voices 0.78 at most. Within a track, clusters were already apart (below 0.65 by construction).
- Grouping at 0.82 and 1.5%: 9 → 4 (later 3, with the user's merges), 19 → 9-10, 10 → 6, never
  joining two differently named speakers. At 0.80 one 3-speaker call collapsed to one: too low.
- Leave-one-out recognition on 28 named speakers: right person best 28/28 at 0.74-0.95; best wrong
  person 0.61 at most.

## Decisions

- Grouping is merges, not new labels: one mechanism for new and old recordings, undone with
  "Separate again", and every view already follows merges.
- It runs once per recording (`speakers_grouped`), so an undone merge stays undone.
- The fragment rule has no 8 s floor (the worker already folds under 8 s) and never folds a
  minute or more of speech.
- Naming by voice reverses "nobody else is named here" from `add-speaker-naming`, at the user's
  request: only with a voice from two recordings, a 0.85 match and a 0.2 lead, and the name does
  not teach the voice (`speakers_by_voice`), so it cannot drift.
- In a call with headphones, two different people whose voices measure 0.82 or more across tracks
  would be joined; measured different voices never came that close, and "Separate again" undoes it.
