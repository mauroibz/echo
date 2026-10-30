## ADDED Requirements

### Requirement: Templates per meeting type
A recording tagged `template:NAME` SHALL be summarized with that template's section guidance in
place of the general one, keeping every other rule. Built-in templates SHALL be `uno-a-uno`,
`entrevista`, `clase` and `cliente`; a Markdown file `~/.config/echo/studio/templates/NAME.md`
SHALL win over a built-in of the same name. The Summary view SHALL offer the templates beside
Summarize and show the one used; `echo-app summarize --template NAME` SHALL do the same. Choosing
a template SHALL set the recording's `template:` tag. Changing the template or its text SHALL mark
the summary out of date.

#### Scenario: An interview
- **WHEN** the user picks "entrevista" beside Summarize
- **THEN** the recording is tagged `template:entrevista`, it is summarized again with one section
  per question, and the view says "entrevista" next to the server

#### Scenario: The user's own template
- **WHEN** `~/.config/echo/studio/templates/directorio.md` exists
- **THEN** "directorio" is offered, and a recording tagged `template:directorio` is summarized with
  that file's guidance
