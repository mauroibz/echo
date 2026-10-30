# Design

## Decisions

- **Placed within the passage.** Passages have start and end times; words do not (the model
  gives none, and aligning words would need a new model). The time is the passage's start plus
  its length times how far into the passage's text the click is, which is close for steady speech,
  minus 0.5 s so the word is heard whole, never before the passage's start.
- **On release, only when nothing is selected**, so dragging over words to select them does not
  move playback, and a click that only places the cursor to edit does, which is what correcting
  along with the audio wants.
- **Playback state kept.** The player's `seek` already restarts from the new place while playing
  and only moves the position while paused, so a click never starts sound by surprise.
