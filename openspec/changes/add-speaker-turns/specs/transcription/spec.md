## ADDED Requirements

### Requirement: Speaker changes inside a passage
When speaker labeling is on and the segmentation model is downloaded, a passage SHALL be cut
where someone other than its main voice speaks for at least 0.4 s, before recognition, so that
the interruption has its own text and speaker. An interruption too short to embed SHALL be
labeled as the nearest speaker other than the one around it. Without the segmentation model,
or for a recording marked as a monologue, passages SHALL be planned and labeled as before.

#### Scenario: Short interruption in a long paragraph
- **WHEN** speaker 1 talks for a minute and speaker 2 says "¿y cuánto sale?" in a short pause
- **THEN** the transcript has speaker 1's text, then a passage of speaker 2 with those words, then speaker 1's text again, each starting a paragraph

#### Scenario: Resume keeps the cuts
- **WHEN** the worker is killed after the cuts were found and transcription resumes
- **THEN** the same passages are transcribed and nothing done is repeated
