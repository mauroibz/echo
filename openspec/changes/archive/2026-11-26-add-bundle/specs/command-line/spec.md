## ADDED Requirements

### Requirement: Bundle from the command line
`echo-app bundle ID...` SHALL print the recordings (a linked set as its parts) as the Markdown
the window's bundle copies, `--parts` SHALL limit it to the parts named, `--timestamps` SHALL
start each passage with its time, and `--out` SHALL write a zip with one note per recording
(`.zip`) or one Markdown file. It SHALL exit with 1 for an unknown id or when there is nothing to
bundle, and with 2 for a part none of the recordings has, naming the parts they have.

#### Scenario: Two meetings to a file
- **WHEN** `echo-app bundle ID1 ID2 --parts summary,actions --out week.zip` runs with Echo Studio installed
- **THEN** `week.zip` holds two notes, each with the meeting's summary and action items and no transcript
