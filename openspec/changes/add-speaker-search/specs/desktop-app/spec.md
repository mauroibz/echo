## ADDED Requirements

### Requirement: Search by speaker
`@name` in the search SHALL limit the results to recordings where a speaker with that name
speaks, where the name is matched by its words from their start, without case or accents, and
`_` joins words of one name; several `@name` SHALL all have to speak. With words as well, the
words SHALL have to be in passages of the named speakers, each result SHALL show the matching
passage text with the speaker's name, and opening a result SHALL find the words only within
those speakers' passages, starting at the first match. Typing `@` SHALL offer the names of the
people who speak in the library. Only speakers the user named, or Echo named as the user, can
be found this way.

#### Scenario: What Ana said about the price
- **WHEN** Ana and Pedro both said "precio" in one meeting, only Pedro did in another, and the user searches `@ana precio`
- **THEN** only the first meeting is listed, with Ana's words under its title, and opening it highlights "precio" in Ana's passages only

#### Scenario: Which meetings was Ana in
- **WHEN** the user searches `@ana`
- **THEN** every recording where a speaker named Ana López speaks is listed
