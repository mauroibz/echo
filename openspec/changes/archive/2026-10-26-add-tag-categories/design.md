# Design

## Decisions

### A naming convention, not a schema

A category is the text before a tag's first colon. Nothing is declared or stored apart from the
tags themselves, so tags stay plain text in `meta.json`, survive a rescan, and old recordings
need no migration. A tag like `10:30` (digits before the colon) counts as a category of its own,
which is harmless. Both sides must be non-empty: `client:` or `:x` are plain tags.

### Category search in the index

`#client:` is matched with `tag_folded LIKE 'client:%'` on the existing `tags` table (folded,
so case and accents do not matter); the colon makes a plain tag named `client` not match. No
schema change.

### The bar

Plain tags keep their place (most used first, up to twelve). Each category is one chip, ordered
by how many recordings carry any of its values; its menu lists "Any category" and then the
values, most used first, each checkable. The search box remains the filter's only state, as for
plain tags.

### Export

Obsidian tags allow letters, digits, `_`, `-` and `/`, with `/` meaning nesting, so `client:Acme`
is written `#client/Acme`.
