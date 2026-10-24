## ADDED Requirements

### Requirement: Speakers
When a recording has more than one speaker, each passage SHALL carry a speaker label. The user
SHALL be able to name a speaker once per recording, and a person named from the dictionary
SHALL be recognized in later recordings as a suggestion the user confirms.

#### Scenario: Two-person interview
- **WHEN** an interview is transcribed and the user names speaker 1 "Lucía"
- **THEN** every passage of speaker 1 shows "Lucía", exports prefix her passages with her name, and her next interview suggests the name
