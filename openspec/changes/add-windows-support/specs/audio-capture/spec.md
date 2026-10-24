## MODIFIED Requirements

### Requirement: Source selection
Echo SHALL list the available audio inputs and let the user choose one, remembering the choice.
On systems with PipeWire it SHALL also list each output as a "Computer audio" source; on other
systems that source is not offered. A missing or unplugged chosen source SHALL fall back to
the default input and say so.

#### Scenario: Windows inputs
- **WHEN** Echo runs on Windows with a USB microphone and a headset
- **THEN** both appear as inputs, the system default is marked, and no "Computer audio" entry is shown
