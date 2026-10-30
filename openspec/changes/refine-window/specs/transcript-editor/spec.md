## MODIFIED Requirements

### Requirement: Show the transcript
The transcript panel SHALL show the user's edited text when it exists, else the corrected
model text with each dictionary correction underlined, else the model text. Each speaker's turn
SHALL be headed by their name with a dot in their color; clicking the name SHALL offer the same
actions as before (name, merge, open profile). Details SHALL offer one optional line, "Who is
speaking, what about", saved with the recording and used as context for its transcriptions.
Under the editor it SHALL show at most one dictionary candidate chip at a time.

#### Scenario: Context line
- **WHEN** the user writes "Entrevista con Lucía sobre PipeWire" in the line in Details and transcribes again
- **THEN** that line precedes the dictionary sentence in the request's context

#### Scenario: Names over turns
- **WHEN** a meeting with Ana and Pedro is shown
- **THEN** each turn starts under the speaker's name, and clicking "Ana" offers to name, merge or open her profile
