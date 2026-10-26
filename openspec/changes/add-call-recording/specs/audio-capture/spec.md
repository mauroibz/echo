## ADDED Requirements

### Requirement: Computer audio alongside the microphone
When the selected source is an input and the backend can record outputs, the user SHALL be able
to also record the computer audio: what the default output plays, following the default output
when it changes. The two SHALL be captured at the same time without taking either device away
from other programs, so a call app keeps its microphone and its sound. The finished recording
SHALL be one lossless file with two channels, the input on the first and the computer audio on
the second, aligned to within 25 ms (to within half a second around
a point where one capture died). Every guarantee of "No audio lost" and "Capture
interruptions" SHALL hold for each track: an interruption of either restarts both into a new
pair of takes and is noted, and if the computer audio cannot be captured the input is still
recorded, with a warning, and the second channel is silent there. While the option is on, a
second level meter SHALL show the computer audio, before and during recording; the silence hint
and the gain apply to the input only. The choice SHALL be remembered.

#### Scenario: Recording a call
- **WHEN** the user turns on computer audio, records while a call plays through the default output and speaks into the microphone, then stops
- **THEN** the recording has two channels, the user's voice on the first and the call on the second, and the call app's sound and microphone worked throughout

#### Scenario: Capture of the computer audio dies
- **WHEN** the computer-audio capture process is killed during a two-track recording
- **THEN** both tracks continue in a new pair of takes within two seconds, the gap is noted, and the finished channels stay aligned

#### Scenario: Supervisor killed
- **WHEN** the recorder supervisor is killed with SIGKILL during a two-track recording
- **THEN** on next start both running captures are adopted, or if they died the takes are finalized, and the recording has both channels up to the kill

#### Scenario: Not offered for a monitor
- **WHEN** the selected source is itself "Computer audio"
- **THEN** the option to add computer audio is not shown and a one-track recording is made
