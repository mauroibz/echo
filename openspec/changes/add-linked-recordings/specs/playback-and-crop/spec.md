## ADDED Requirements

### Requirement: Playing a set
When a set is selected, the player SHALL play its parts' cropped audio back to back on one
timeline, show the parts' waveforms end to end with their boundaries marked, and seek across
parts by clicking the waveform or Ctrl+clicking the text. Cropping and adding markers SHALL be
done on a single part.

#### Scenario: Continuing into the next part
- **WHEN** the user plays a set of three voice notes from the start
- **THEN** playback continues from the end of the first note into the second and third without the user doing anything, and the playhead and the highlighted passage follow
