## MODIFIED Requirements

### Requirement: Model provenance
Each transcript SHALL record the model and adapter repositories and revisions used, whether the
adapter was enabled, the language, the creation time, and the context sentence given to the
model, if any.

#### Scenario: Inspect provenance
- **WHEN** a transcript is created with the adapter enabled and a dictionary context
- **THEN** its stored data names both revisions and the exact context sentence
