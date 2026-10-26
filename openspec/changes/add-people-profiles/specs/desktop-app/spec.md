## ADDED Requirements

### Requirement: People and profiles
A People window SHALL list every person in the dictionary and everyone named as a speaker, with
the number of recordings they speak in, filtered by typing. A person's profile SHALL show and
save free notes, their aliases, their tags, and their recordings with how long they spoke in
each, newest first; opening one SHALL show that recording in the main window. Where their voice
is known, the profile SHALL play a few seconds of them and offer to forget the voice. The
profile SHALL also open from a speaker's name in the transcript.

#### Scenario: From a speaker to everything about them
- **WHEN** the user clicks "Ana" beside a passage and chooses "Open profile"
- **THEN** Ana's profile lists the three calls she speaks in with her speaking time in each, the user writes "CFO de Acme" in her notes and tags her `client:Acme`, and after restarting Echo both are still there
