## ADDED Requirements

### Requirement: Correcting speakers in the text
From the transcript's context menu the user SHALL be able to say who said a paragraph, or a
selection of words, choosing one of the recording's speakers or someone new. A selection that
covers whole passages SHALL relabel them; one that covers part of a passage SHALL split it, the
selected words becoming a paragraph of their own with the chosen speaker. The user SHALL be able
to undo a fix and to join a paragraph with the one above. Labels, exports with estimated times
for split text, search by speaker and people's speaking times SHALL follow the fixes. Fixes SHALL
be stored with the passage, speaker, name, the words and estimated times of a split, and the
transcript they apply to; a new transcription SHALL keep them without applying them.

#### Scenario: An interruption
- **WHEN** Ana's passage reads "El precio sube ¿cuánto? un diez por ciento" and the user selects "¿cuánto?" and chooses Said by → Pedro
- **THEN** the passage shows as three paragraphs labeled Ana, Pedro and Ana, the TXT export reads the same, and searching `@pedro cuánto` finds the recording

#### Scenario: A paragraph given to the wrong person
- **WHEN** the user right-clicks a paragraph labeled Pedro and chooses Said by → Ana
- **THEN** it is labeled Ana, and if the paragraph above is Ana's the margin shows one label for both
