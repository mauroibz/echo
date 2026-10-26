## MODIFIED Requirements

### Requirement: Playback
The user SHALL be able to play, pause, seek by clicking the waveform or with the keyboard, set
the speed (1x, 1.25x, 1.5x, 2x) and set the volume from 0% to 400%. Above 100% the sound SHALL
be boosted without clipping. The volume SHALL change only what is heard: the audio file, exports
and transcription stay the same. Every format that can be imported or recorded SHALL play. A
recording with a microphone and a computer-audio track SHALL play both tracks in both ears, each
at its recorded level, without clipping where they overlap.

#### Scenario: Play a voice note
- **WHEN** the user selects an imported `.opus` voice note and presses play
- **THEN** it plays and the playhead moves on the waveform

#### Scenario: Boost a quiet meeting
- **WHEN** the user drags the volume of a quiet meeting to 300% during playback
- **THEN** playback continues from the same place, louder, with no clipped samples, and the file's hash is unchanged

#### Scenario: Play a recorded call
- **WHEN** the user plays a recording made with computer audio
- **THEN** their own voice and the call are heard together in both ears

### Requirement: Waveform
A waveform of the whole recording SHALL be shown and computed in the background, cached so that it
appears immediately the next time. For a recording with a computer-audio track it SHALL show the
two tracks mixed.

#### Scenario: Long recording
- **WHEN** a two-hour recording is selected for the first time
- **THEN** the player is usable at once and the waveform appears when computed

### Requirement: Export audio
The user SHALL be able to export the recording's audio. With a crop, the export SHALL be a new
lossless FLAC file of the cropped span; without one, a copy of the original file. A recording with
a computer-audio track SHALL keep its two channels in the export.

#### Scenario: Export cropped
- **WHEN** a cropped recording is exported
- **THEN** the exported file contains exactly the cropped span and the original is unchanged
