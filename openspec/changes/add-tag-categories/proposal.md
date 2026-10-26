# Proposal

## Why

Tags are one flat list. With calls from several clients and projects, the chip bar fills with
names that belong to a few kinds (client, project, type of meeting) and the most used twelve
crowd out the rest. Filtering "every call with Acme" or "every standup" works, but nothing shows
that Acme and Globex are both clients, and "any client" cannot be asked at all.

## What Changes

- **`category:value` tags.** A tag with a colon, such as `client:Acme`, `project:Echo` or
  `type:standup`, belongs to the category before the colon. Tags without one stay as they are.
  They are plain text in `meta.json`, as now.
- **The chip bar groups them.** One chip per category ("client ▾") opens its values to pick from,
  plus "Any client"; plain tags show as now. In the tag editor a categorized tag shows its
  category dimmed, and typing `client:` completes the values used before.
- **Search.** `#client:acme` finds that value; `#client:` finds recordings with any value of the
  category. The same works in `echo-app list --tag`.
- **Markdown export** writes `client:Acme` as the nested tag `#client/Acme`, the form Obsidian and
  most Markdown tools understand.

Out of scope: renaming a category across recordings, colors per category, a category's values
being fixed in advance.

## Capabilities

### Modified Capabilities
- `desktop-app`: the tag bar groups categories.
- `library-storage`: categorized tags and searching a whole category.

## Impact

`library.py` (splitting a tag), `index.py` (category filter, counts), `ui/tags.py` (grouped bar,
dimmed category in chips), `ui/main_window.py`, `export.py`, `cli_tr.py` help, `README.md`,
`docs/design.md`, `CHANGELOG.md`. No new dependencies.
