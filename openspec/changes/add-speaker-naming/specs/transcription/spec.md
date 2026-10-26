## ADDED Requirements

### Requirement: The user is named automatically
Once the user has said which speaker is them, Echo SHALL know their name and voice, and SHALL
name them itself in later recordings: a speaker whose voice matches the user's, and in a recorded
call the one speaker on the microphone track. A name the user gave a speaker SHALL never be
replaced. The voices SHALL stay on this computer.

#### Scenario: Second recording
- **WHEN** the user answers "It's me" for speaker 1 of one recording, then records and transcribes another
- **THEN** in the new recording the user's passages carry their name without any question

#### Scenario: A call
- **WHEN** a call recorded with computer audio is transcribed and one speaker is on the microphone track
- **THEN** that speaker carries the user's name, whether or not their voice was learned yet
