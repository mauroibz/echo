## ADDED Requirements

### Requirement: Language per recording
Each transcription SHALL use the recording's language, defaulting to the global setting, and
SHALL apply the Spanish adapter only when the language is Spanish. The available languages
SHALL be those the pinned model supports.

#### Scenario: English voice note
- **WHEN** the user sets a recording's language to English and transcribes it
- **THEN** the transcript is English, the adapter is recorded as not enabled, and the style sentence used is the English one
