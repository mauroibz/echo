## ADDED Requirements

### Requirement: A person's part in each meeting
After a recording with named speakers is summarized, Studio SHALL save one line per named person
on what they contributed, from one request for all of them, in `parts.json`. A failure SHALL leave
the summary and the action items saved.

#### Scenario: Three people in a sync
- **WHEN** a meeting where Sofía, Diego and Carla are named is summarized
- **THEN** one request returns a line for each, and Sofía's says she took on the test plan

### Requirement: A person's page
Studio's People SHALL list everyone Echo knows, filtered by name or email. A person's page SHALL
show their email (editable, one person per email), their meetings newest first with the minutes'
excerpt and their part, the action items assigned to them without any done state, and their
notes. Opening a speaker's profile SHALL open this page while Studio's rail is shown.

#### Scenario: Before talking to Sofía
- **WHEN** the user opens Sofía's page
- **THEN** it shows sofia@ejemplo.com, her two meetings with what she did in each, and the two items assigned to her
