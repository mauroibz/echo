# playback-and-crop Specification

## Purpose
Lets the user listen to any recording, see its shape, and trim unwanted parts without ever
changing the original audio.

## Requirements

### Requirement: Playback
The user SHALL be able to play, pause, seek by clicking the waveform or with the keyboard, and set
the speed (1x, 1.25x, 1.5x, 2x). Every format that can be imported or recorded SHALL play.

#### Scenario: Play a voice note
- **WHEN** the user selects an imported `.opus` voice note and presses play
- **THEN** it plays and the playhead moves on the waveform

### Requirement: Waveform
A waveform of the whole recording SHALL be shown and computed in the background, cached so that it
appears immediately the next time.

#### Scenario: Long recording
- **WHEN** a two-hour recording is selected for the first time
- **THEN** the player is usable at once and the waveform appears when computed

### Requirement: Non-destructive crop
The user SHALL be able to set crop start and end by dragging handles on the waveform or at the
playhead, nudge them with the keyboard, and clear them. Handles SHALL snap to nearby pauses unless
Shift is held. Playback and transcription SHALL use only the cropped span. The original audio
file SHALL never be modified.

#### Scenario: Trim the beginning
- **WHEN** the user drags the start handle to 0:42
- **THEN** playback starts at 0:42, the area before is shaded, the original file's hash is unchanged,
  and a re-transcription covers only the cropped span

### Requirement: Export audio
The user SHALL be able to export the recording's audio. With a crop, the export SHALL be a new
lossless FLAC file of the cropped span; without one, a copy of the original file.

#### Scenario: Export cropped
- **WHEN** a cropped recording is exported
- **THEN** the exported file contains exactly the cropped span and the original is unchanged

### Requirement: Markers on the waveform
Markers SHALL be drawn on the waveform with their notes on hover, SHALL be movable and
removable there, and SHALL be addable at the playhead. Playback SHALL jump to the next or
previous marker with one shortcut.

#### Scenario: Jump between markers
- **WHEN** the user presses the next-marker shortcut during playback
- **THEN** playback continues from the next marker and the transcript follows

### Requirement: Playing a set
When a set is selected, the player SHALL play its parts' cropped audio back to back on one
timeline, show the parts' waveforms end to end with their boundaries marked, and seek across
parts by clicking the waveform or Ctrl+clicking the text. Cropping and adding markers SHALL be
done on a single part.

#### Scenario: Continuing into the next part
- **WHEN** the user plays a set of three voice notes from the start
- **THEN** playback continues from the end of the first note into the second and third without the user doing anything, and the playhead and the highlighted passage follow
