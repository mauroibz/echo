## MODIFIED Requirements

### Requirement: Follow along
While unedited model text is shown, the passage being played SHALL be highlighted, and clicking a
passage with Ctrl held SHALL move playback to its start and play. A plain click that selects
nothing SHALL move playback near the clicked word, placed by how far into its passage it is and
a little before it, without starting or stopping playback; dragging to select text SHALL not
move playback.

#### Scenario: Ctrl+click to seek
- **WHEN** the user Ctrl+clicks the third paragraph
- **THEN** playback jumps to the start of that passage

#### Scenario: Click a word
- **WHEN** playback is paused and the user clicks a word halfway through a passage
- **THEN** the playhead moves to about halfway through that passage's time, still paused, and
  Space plays from there
