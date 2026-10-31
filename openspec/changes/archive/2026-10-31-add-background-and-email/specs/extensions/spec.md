## ADDED Requirements

### Requirement: Recording for an extension
The window SHALL let an extension start a recording from the current source, with a title, stop
it, and ask which recording is being made. Starting SHALL do nothing while a recording is being
made or starting.

#### Scenario: A meeting starts
- **WHEN** an extension starts a recording titled "Roadmap review"
- **THEN** Echo records as if Record were pressed, the recording is named "Roadmap review", and a second start is refused until it stops
