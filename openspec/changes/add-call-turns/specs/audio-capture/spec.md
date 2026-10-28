## ADDED Requirements

### Requirement: The call's track is not moved with the microphone
The capture of the computer audio SHALL identify itself to the audio server apart from the
microphone's capture, so that moving Echo's microphone to another source (a noise gate's, for
example) does not move the computer audio there in later recordings.

#### Scenario: A noise gate on the microphone
- **WHEN** the user has moved Echo's microphone capture to a noise gate's virtual source once, and records a call
- **THEN** the microphone track has the gated microphone and the computer track has the call
