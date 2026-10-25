## MODIFIED Requirements

### Requirement: Playback
The user SHALL be able to play, pause, seek by clicking the waveform or with the keyboard, set
the speed (1x, 1.25x, 1.5x, 2x) and set the volume from 0% to 400%. Above 100% the sound SHALL
be boosted without clipping. The volume SHALL change only what is heard: the audio file, exports
and transcription stay the same. Every format that can be imported or recorded SHALL play.

#### Scenario: Play a voice note
- **WHEN** the user selects an imported `.opus` voice note and presses play
- **THEN** it plays and the playhead moves on the waveform

#### Scenario: Boost a quiet meeting
- **WHEN** the user drags the volume of a quiet meeting to 300% during playback
- **THEN** playback continues from the same place, louder, with no clipped samples, and the file's hash is unchanged
