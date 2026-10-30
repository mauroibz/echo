# Follow-up draft

## Why

After a meeting someone writes the email with what was agreed and who does what. The summary
and the action items already hold it.

## What Changes

- "Follow-up" in the Summary view drafts a short email from the summary and the open action
  items, in the recording's language, and opens it in a box to edit, with Copy and Open in mail
  (a `mailto:` link to the user's mail program). Studio sends nothing and holds no mail account.
- `echo-app summarize ID --follow-up` prints the draft.

## Capabilities

### New Capabilities

- `studio-follow-up`

## Impact

`src/echo_studio/followup.py` (new), `ui.py` (`FollowUpDialog`), `cli.py`, `tests/test_studio.py`,
`docs/guide.md`.
