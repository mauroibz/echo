# Design

## Decisions

- **No embeddings.** Plain search over the FTS5 index already covers text and speakers, which
  keeps Studio lean; embeddings come back only if measured answers miss what search finds.
- **The model writes the searches,** since a question's words are rarely the words said ("¿qué
  acordamos?" vs. "quedamos en"). Searches are prefix matches of every word, so short searches
  find more; the prompt asks for variants as separate searches. If the reply is not a list, the
  question itself is the search.
- **At most 60 passages,** each with one passage either side, in the order the searches find
  them (newest recordings first within each).
- **Only the passages leave the computer,** not whole transcripts; the screen says so.
