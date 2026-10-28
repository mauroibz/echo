## ADDED Requirements

### Requirement: Speaker changes inside a passage
When speaker labeling is on and the segmentation model is downloaded, a passage SHALL be cut
where someone other than its main voice speaks for at least 0.4 s, before recognition, so that
the interruption has its own text and speaker. An interruption too short to embed SHALL be
labeled as the nearest speaker other than the one around it. Without the segmentation model,
or for a recording marked as a monologue, passages SHALL be planned and labeled as before. A
passage shorter than 1.5 s whose whole text is what the model says for audio it cannot make out
("Gracias." in Spanish) SHALL be shown without text.

#### Scenario: Short interruption in a long paragraph
- **WHEN** speaker 1 talks for a minute and speaker 2 says "¿y cuánto sale?" in a short pause
- **THEN** the transcript has speaker 1's text, then a passage of speaker 2 with those words, then speaker 1's text again, each starting a paragraph

#### Scenario: A fragment the model cannot make out
- **WHEN** a 0.5 s piece cut out of a passage comes back from the model as "Gracias."
- **THEN** the transcript shows no text for it, and the audio is still there to play

#### Scenario: Resume keeps the cuts
- **WHEN** the worker is killed after the cuts were found and transcription resumes
- **THEN** the same passages are transcribed and nothing done is repeated
