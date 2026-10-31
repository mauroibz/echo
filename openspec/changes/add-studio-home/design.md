# Design

The look was agreed on mockups (2026-10-31): a narrow deep rail of icons with a round coral
Record; each Studio page opens with a deep band on a slant whose bottom is Lagoon's swells and a
canvas-colored wave; large display type (the next meeting's time at six times the UI size);
minutes as a timeline with the date at the left and borderless cards.

## Decisions made while implementing

- Studio's window is a subclass that takes Echo's central widget into a page: no change in
  Echo's base was needed beyond `start_recording` and the hooks already there.
- The rail and the hero restyle on a palette change only when the theme's tokens changed, since
  setting a style sheet sends another palette change.
- The meeting page of the mockups is Echo's recording page opened on the Minutes view, so the
  transcript, player and details stay one click away.
- A person's meetings include recordings whose event invited their email, besides those they
  speak in, so a meeting with an unnamed speaker still shows on their page.
