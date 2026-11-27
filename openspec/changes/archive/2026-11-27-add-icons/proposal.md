# Icons for recordings and collections

## Why

With many recordings and several collections, titles alone are slow to scan. A mark in a color
before a title, or in place of a collection's folder, is found at a glance.

## What Changes

- Icon… in a recording's, a selection's and a collection's menu: a picker with six colors and 40
  symbols, and "No icon".
- 32 more Lucide symbols bundled (same set and license as the ones Echo has), two colors (`lilac`,
  `lime`) added to the theme for the deep sidebar.
- `icon` in a recording's `meta.json` and JSON; collections' icons in `<data>/collections.json`.

## Capabilities

### Modified Capabilities

- `desktop-app`, `library-storage`

## Impact

`src/echo_app/collections.py`, `library.py`, `cli.py`, `cli_json.py`, `ui/collections.py`,
`ui/library_view.py`, `ui/window_collections.py`, `ui/window_library.py`, `ui/recorder_panel.py`,
`ui/theme.py`, `ui/assets/icons/`; `tests/test_collections.py`; `docs/guide.md`, `docs/design.md`,
`CHANGELOG.md`. No new dependency.
