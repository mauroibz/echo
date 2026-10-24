## ADDED Requirements

### Requirement: Sets in the list
A set SHALL appear as one row in the list, placed by its newest part, showing its title, the
number of parts, the total length and a status summarizing the parts, and SHALL expand to show
its parts as indented rows. A search or tag filter SHALL show a set when any of its parts
matches, with the matching parts shown.

#### Scenario: Expanding a set
- **WHEN** the user clicks the chevron of a set of three voice notes
- **THEN** the three parts appear beneath it in order, and selecting one shows that recording alone

### Requirement: Linking recordings
The user SHALL be able to link recordings by selecting several rows and pressing Link (or
Ctrl+L), and by dragging a row onto another row or onto a set; to reorder parts by dragging or
with Alt+Shift+Up and Alt+Shift+Down; and to unlink from the context menu or by dragging a part
out. Deleting a set row SHALL ask whether to unlink the set, which is the default, or move all
its parts to the trash.

#### Scenario: Link three selected recordings
- **WHEN** the user Ctrl+clicks three voice notes and presses Link
- **THEN** one set row replaces them, ordered by date, and it is selected with the three transcripts shown one under the other

#### Scenario: Deleting a set
- **WHEN** the user presses Delete on a set row and confirms with the default button
- **THEN** the set is unlinked and its parts are listed as separate recordings again

### Requirement: Offer to link a burst
After an import, voice notes that look like one burst SHALL be offered for linking in a
single-line banner above the list with a one-click Link action and a dismiss button. An offer
SHALL never link without the click, and a dismissed offer SHALL NOT be shown again.

#### Scenario: Three consecutive WhatsApp notes
- **WHEN** the user drops PTT-20261023-WA0004, WA0005 and WA0006 on the window
- **THEN** after the import a banner offers to link the three voice notes, and one click on it creates the set
