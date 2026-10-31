# Design

## The file

`actions.json` goes to version 2. Each item keeps `text`, `owner`, `due` and `at`, and gains:

- `context`: the user's line, or "".
- `discarded`: true when the user threw it out. It stays in the file so summarizing again does
  not bring it back and so it can be restored.
- `edited`: true once the user changed text, owner or due date.
- `origin`: `"model"` or `"user"` (added by hand).
- `key`: the folded text the model first gave it. Edits change `text`, not `key`, so a summary
  made again can still find the item.

`done` is gone. A version 1 file is read as version 2 with every item `origin: "model"`,
`key` from its text, and its done flag dropped.

## Summarizing again

The new extraction gives a fresh list. For each new item whose folded text equals an old
model item's `key`, the old item's `text`, `owner`, `due`, `context`, `discarded` and `edited`
win when the old one was edited, had context or was discarded; `at` comes from the new one when
the old had none. Old `user` items are appended unchanged. Old model items with no match are
dropped, as before: they were the model's, and the new summary no longer has them.

## The UI

Items stay in the Summary view, under the minutes. Each row has the text, a line with owner,
"by <date>", "edited" when it is, the context in the dim style, the time pill, and two small
buttons: edit (pencil) and discard (x). Edit turns the row into fields (text, owner as an
editable combo of the recording's speakers, due date as YYYY-MM-DD, context) with Save and
Cancel. Discarded items fold into one line under the list, "N discarded · Show", which lists
them with Restore. "+ Add" above the list opens an empty editor.

The People section keeps its place and lists the person's items that are not discarded, newest
first, with the time pill; no checkboxes and no edit there, since the minutes are where items
are polished.

## Decisions made while implementing

- The editor's due date is a plain `YYYY-MM-DD` field (Save stays off for anything else), not a
  date picker: most items have no date, and a picker has no "none".
- Rows are taken out of the list at once (`setParent(None)`) when it is rebuilt, so the editor
  that replaces a row is the only one a test or an accessibility tool finds.
