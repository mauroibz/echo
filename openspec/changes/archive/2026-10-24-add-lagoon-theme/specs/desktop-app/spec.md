## ADDED Requirements

### Requirement: Visual identity and appearance
Echo SHALL ship its own look, independent of the desktop theme: bundled icons and interface
typeface, a deep sidebar with the recorder and library, and the selected recording on light
cards. Light SHALL be the default appearance; the user SHALL be able to choose dark or to follow
the system, and the change SHALL apply without restarting. Recording SHALL be signalled in coral
in the recorder, the library row and the window title. Animation SHALL stop when there is
nothing to show (no input and no recording) and while the window is hidden.

#### Scenario: Switching appearance
- **WHEN** the user picks Dark in Settings
- **THEN** every open window repaints in the dark palette, including icons and custom-drawn parts
- **AND** cancelling the dialog restores the appearance that was showing before

#### Scenario: Same look on any desktop
- **WHEN** Echo runs on a machine without the Breeze icon theme or the Manrope font
- **THEN** it shows the same icons and typeface as on the developer's machine

#### Scenario: Waves follow the input
- **WHEN** the selected input picks up sound before or during a recording
- **THEN** the waves under the recorder rise with the level, and settle when the input is silent
