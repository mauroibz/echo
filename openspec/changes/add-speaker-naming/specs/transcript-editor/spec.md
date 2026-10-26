## ADDED Requirements

### Requirement: Naming speakers from a prompt
When the shown recording has speaker labels and an unnamed speaker, a bar above the transcript
SHALL ask about one unnamed speaker at a time, the one with the most speech first. When the
speaker's voice matches a person named before, it SHALL offer that person in one click;
otherwise it SHALL offer a name field with the dictionary's people. While no speaker of the
recording is the user, it SHALL also offer "It's me". It SHALL offer a way to hear a few seconds of that speaker, and "Not now", which hides the bar for that
recording for good. Naming SHALL move the bar to the next unnamed speaker. The bar SHALL NOT take
keyboard focus, SHALL NOT block editing or playback, SHALL NOT appear while the dictionary
suggestion is shown or for a linked set's combined view, and SHALL disappear when every speaker
is named.

#### Scenario: A known voice
- **WHEN** a meeting is transcribed and speaker 2's voice matches Ana, named in an earlier recording
- **THEN** the bar says speaker 2 sounds like Ana, and one click names every passage of speaker 2 "Ana" and the bar moves to the next unnamed speaker

#### Scenario: Hearing before naming
- **WHEN** the bar asks who speaker 3 is and the user presses ▶
- **THEN** a few seconds of speaker 3's longest passage play, and the user types "Pedro" and presses Enter to name them

#### Scenario: Not now
- **WHEN** the user presses "Not now"
- **THEN** the bar is gone for that recording, also after restarting Echo, and the speakers stay nameable from the margin
