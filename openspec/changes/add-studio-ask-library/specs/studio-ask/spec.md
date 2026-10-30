## ADDED Requirements

### Requirement: Ask the library
With a server set, an Ask screen SHALL answer questions across recordings: the question SHALL be
turned into searches of Echo's index, only the matching passages SHALL be sent to the server, and
the answer SHALL cite them; choosing a citation SHALL open its recording playing from the
passage. When nothing matches, the screen SHALL say so without asking the model.
`echo-app ask "question"` SHALL print the answer and the cited passages.

#### Scenario: Across meetings
- **WHEN** the user asks "¿qué acordamos con Acme sobre precios?" on the Ask screen
- **THEN** the answer cites passages from the recordings that mention it, and choosing [2] opens
  the second one's recording at that passage
