## ADDED Requirements

### Requirement: Fixes teach the rest of the recording
After the user says who said a passage, or undoes such a fix, Echo SHALL reassign the other
passages of the recording that have a voiceprint: a passage SHALL move to another speaker only
when it sounds clearly closer to that speaker as the user's fixes now describe them, and in a
recorded call only to a speaker on its own track. A short passage that took its speaker from the
passage before SHALL follow it. Echo SHALL say how many passages moved. The reassignment SHALL
be stored apart from the model's transcript, labels, exports, search and people SHALL follow it,
and "Back to the speakers Echo found" SHALL remove it. A new transcription SHALL drop it.

#### Scenario: Two people found as one
- **WHEN** speaker 2's passages are Pedro and Lucía, and the user chooses Said by → Someone else… "Lucía" on one of Lucía's paragraphs
- **THEN** the other passages in Lucía's voice are labeled Lucía too, and the status bar says how many moved

#### Scenario: Back to Echo's labels
- **WHEN** the user chooses "Back to the speakers Echo found" on a speaker's label
- **THEN** every passage has the speaker the transcription gave it, except the passages the user fixed

### Requirement: A voice is learned once per recording
A person's stored voice SHALL be the mean of one part per recording they were named in. Naming
them again in the same recording (after a new transcription, a rename or a merge) SHALL replace
that recording's part, and renaming a speaker to someone else, or merging it into another
person, SHALL take its part out of the old name's voice.

#### Scenario: Named wrong, then right
- **WHEN** the user names speaker 4 "Lucía", transcribes again twice and names it "Lucía" each time, then renames it "Ana"
- **THEN** Lucía's voice holds nothing from this recording and Ana's holds it once
