# Design

## Decisions made while implementing

- **Symbols, not emoji.** Emoji were built first and drew as nothing: this Qt resolves them to the
  system's color emoji font and cannot draw it (see Collections in `docs/design.md` for what was
  measured). Bundled symbols in theme colors need no font and match the rest of the window.
- **A collection's icon is in `collections.json`**, since a collection has no file of its own and an
  icon repeated in every member's `meta.json` could disagree with itself. The file holds only looks.
- **The picker answers on the symbol click**, with the color chosen first, so the usual case is two
  clicks and there is no OK button.
- Linked sets get no icon: a set already has its own mark in the list.
- The downloaded SVGs were rewritten to the bundled one-line form keeping only plain shapes.
