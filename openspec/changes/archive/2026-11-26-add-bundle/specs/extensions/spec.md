## MODIFIED Requirements

### Requirement: Where extensions add
An extension SHALL be able to add command-line subcommands, setup checks, sections to a
recording's Markdown note, parts to choose for a recording's bundle, Settings pages, views next to the transcript, actions to the window,
the names offered first when naming a recording's speakers, and to replace the main window with
a subclass that lays out the same parts. The window SHALL signal when a recording's transcript
is written.

#### Scenario: A view next to the transcript
- **WHEN** an extension adds a view titled "Summary"
- **THEN** a switch with Transcript and Summary appears over the transcript, and the view is told which recording is selected each time the selection changes

#### Scenario: A section in exported notes
- **WHEN** an extension returns a section for a recording and the recording is exported as Markdown
- **THEN** the note has that section after its header and before the transcript

#### Scenario: A part in a bundle
- **WHEN** an extension offers a "Summary" part for a recording and the user bundles that recording
- **THEN** the dialog lists Summary beside Transcript, and the bundle has it under its heading before the transcript when ticked
