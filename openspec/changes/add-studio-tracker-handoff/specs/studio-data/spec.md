## ADDED Requirements

### Requirement: Sending from the command line
`echo-app actions --ready` SHALL list the items the user marked ready and not sent.
`echo-app item ID ITEM --sent REF [--url URL]` and `echo-app item ID ITEM --failed REASON` SHALL
record what happened to a ready item named by uid or index. They SHALL exit 1 for an unknown
recording or item, or an item that is not ready, and 2 without `--sent` or `--failed`.

`echo-app meetings --unprocessed` SHALL list the meetings not processed. The JSON SHALL carry each
item's uid, state, tracker reference and failure, and each meeting's tracker status: when it was
marked ready, whether it is processed, and how many items are in each state.

#### Scenario: A nightly sync
- **WHEN** a script runs `echo-app actions --ready --json`, creates each item in its tracker and runs `echo-app item ID UID --sent REF --url LINK`
- **THEN** the next `actions --ready` lists none of them, and the meetings whose items are all sent are no longer in `meetings --unprocessed`
