## Decisions

- **A card under the pill, not a popup.** The dock is a frameless tool window; a popup would be
  another window to place on Wayland. The dock's own layout grows by a card painted like the
  pill (`_Deep`), so it moves and stays above (where it can) with it.
- **Saved as typed.** 800 ms after the last key, and at once when the card folds, the dock hides
  or the recording stops: the dock is used while the window is gone, so there is no "focus
  leaves" moment to save on as Details has.
- **While the card is open the dock does not shrink** to the time, so it does not fold under the
  user's typing.
- **N toggles it.** Typed keys go to the text field first (Qt's shortcut override), so N and M
  inside the notes are letters.
- **Quick notes keep the window.** They are a few seconds of dictation from another
  application; the setting is about recordings the user sits through.

## Decisions made while implementing

- The Briefing's field kept a copy from when the recording started and wrote it back on every
  refresh when it differed, which would have erased notes typed in the dock. It now saves only
  text that differs from what it loaded.
