## ADDED Requirements

### Requirement: Watched folders
Echo SHALL import new audio files that appear in the user's watched folders while it runs and
on start, once each file has stopped changing, leaving the original in place and skipping
duplicates. Failures SHALL be reported once per file and not retried on every scan.

#### Scenario: Phone sync drops a voice note
- **WHEN** a `.opus` voice note appears in a watched folder
- **THEN** within ten seconds it is in the library with its WhatsApp date and, if enabled, queued for transcription
