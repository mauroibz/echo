## ADDED Requirements

### Requirement: Ask a recording
With a server set, an Ask view beside the transcript SHALL answer questions about the shown
recording from its transcript, saying when the transcript does not answer, and cite the times its
statements come from; choosing a cited time SHALL play the recording from there. Earlier
questions about the same recording SHALL be part of the context until another recording is shown.
`echo-app ask ID "question"` SHALL print the answer.

#### Scenario: Where was the price agreed
- **WHEN** the user asks "¿qué precio se acordó?" in the Ask view
- **THEN** the answer cites a time such as [12:30], and choosing it plays the recording from 12:30
