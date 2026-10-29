## ADDED Requirements

### Requirement: Echo alone is unchanged
Without an extension package, Echo SHALL behave and look as it does without this capability:
no added menus, tabs, views, commands or checks. The core SHALL never import an extension
package and SHALL open no network connection other than downloading its models.

#### Scenario: No extension present
- **WHEN** Echo starts from a checkout with no extension package
- **THEN** the window, Settings, `echo-app --help` and `echo-app doctor` are the same as before this change

#### Scenario: Core stays offline
- **WHEN** the test suite runs
- **THEN** it fails if a core module imports an extension package or a network library outside the model download

### Requirement: Extensions are optional and contained
Echo SHALL load the known extension packages that are present, and SHALL start without an
extension whose import or hook raises, logging the error. `ECHO_NO_EXTENSIONS=1` SHALL start Echo
without any extension.

#### Scenario: Broken extension
- **WHEN** an extension raises while it is imported
- **THEN** Echo starts, records and transcribes as usual, and the log has the traceback

### Requirement: Where extensions add
An extension SHALL be able to add command-line subcommands, setup checks, sections to a
recording's Markdown note, Settings pages, views next to the transcript, actions to the window,
and to replace the main window with a subclass that lays out the same parts. The window SHALL
signal when a recording's transcript is written.

#### Scenario: A view next to the transcript
- **WHEN** an extension adds a view titled "Summary"
- **THEN** a switch with Transcript and Summary appears over the transcript, and the view is told which recording is selected each time the selection changes

#### Scenario: A section in exported notes
- **WHEN** an extension returns a section for a recording and the recording is exported as Markdown
- **THEN** the note has that section after its header and before the transcript
