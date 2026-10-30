## ADDED Requirements

### Requirement: Titles from the summary
After a recording is summarized, if its title is still automatic and the setting "Give recordings
you did not name a short title from their summary" is on (the default), Studio SHALL replace the
title with one of at most 8 words made from the summary. A title the user typed SHALL never be
replaced, including one typed while the request ran.

#### Scenario: An unnamed meeting
- **WHEN** a recording titled with its first sentence is summarized
- **THEN** its title becomes a short description of the meeting

#### Scenario: A named one
- **WHEN** the user named the recording and it is summarized
- **THEN** its title is unchanged and no title is requested
