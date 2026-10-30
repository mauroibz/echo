# Design

## Decisions

- **The whole timed transcript,** up to 150,000 characters (about three hours of talk), since the
  model can then answer from anywhere in it; a longer one sends the lines with the question's
  words and three lines either side.
- **History folded into one message.** `llm.complete` takes a system prompt and one message;
  earlier questions and answers go at the end of it, before the question, rather than adding a
  second request format for both kinds of server.
- **A view, not a box in the Summary view,** so the summary keeps its room and the conversation
  has all of it.
- **Citations are `echo:ID@SECONDS` links** in the rendered Markdown; the view catches them and
  calls `show_recording`.
