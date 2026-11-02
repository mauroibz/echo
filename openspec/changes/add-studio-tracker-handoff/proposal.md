## Why

The action items are polished in Echo to go to a team tracker (Plane, Trello, Jira), but there was
no way to say which ones were approved, to learn which ones made it, or to know that a call is
done with and can be archived. Each team sends items its own way, usually with an agent that knows
its projects and people, so Echo should hand the items over and keep what comes back, without
knowing any tracker.

## What Changes

- **Item states.** Each item is proposed, ready, sent or failed, and has a `uid` that survives
  summarizing again.
- **Ready to send.** Under the minutes, Ready to send… lists the items that will go and, once
  confirmed, marks every item not discarded ready. Back to review takes them back.
- **Sent and failed.** A sent item shows its tracker reference as a link and can no longer be
  changed in Echo. A failed one says why, and marking the meeting ready again resends it.
- **Processed meetings.** A meeting is processed once it was marked ready and every item left
  is sent; a meeting with nothing to send is processed with Mark processed. The minutes' bar
  and the meeting's card on the Briefing say so.
- **Command line.**
  - `echo-app actions --ready` lists the approved items.
  - `echo-app item ID UID --sent REF [--url URL]` and `--failed REASON` record what happened.
  - `echo-app meetings --unprocessed` lists the meetings not processed yet.
  - The JSON gains `uid`, `state`, `tracker`, `failure` and the meeting's `tracker` status.
- The agent skill explains how to send the items, for any tracker.
- Summarizing again never changes ready, sent or failed items, and keeps them even if the model
  no longer lists them.

## Impact

- Code: `src/echo_studio/actions.py`, `actions_ui.py`, `ui.py`, `home.py`, `data.py`,
  `cli.py`.
- Files: `actions.json` items gain `uid`, `state`, `tracker` and `failure`, and the file gains
  `ready_at`. Files without them read as proposed, with a uid made from each item's key.
- No new dependency. Echo talks to no tracker.
