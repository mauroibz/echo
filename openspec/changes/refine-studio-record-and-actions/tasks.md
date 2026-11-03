## 1. Data

- [x] 1.1 `done` on items: `set_done`, kept by `merge`, read from version 1 files; tests
- [x] 1.2 `set_send` (ready/proposed per item, failed back to ready), `mark_reviewed`; processed =
  reviewed with nothing ready or failed; `mark_ready`/`unmark_ready` removed; tests
- [x] 1.3 Command line: `done` in the JSON, `[x]` in the text, help and agent skill reworded

## 2. Window

- [x] 2.1 Action items view beside Minutes, with the count on its tab, the send bar with Mark
  reviewed / Reopen, and polling for the sender's writes; Minutes shows the summary alone; tests
- [x] 2.2 Item rows: done checkbox, To tracker switch (accent), failure line; person page too; tests
- [x] 2.3 Rail: Record at the top with the waveform and the clock; Briefing's house icon; tests
- [x] 2.4 Briefing: Record this meeting in the hero only for a meeting under way (no Record now);
  cards with done and to-send counts, their items open the Action items view; tests
- [x] 2.6 Opaque scroll contents in Action items, Briefing and People; paint counts measured; a test
- [x] 2.7 No instruction paragraph: tooltips on the checkbox, switch, edit, discard, Add, count and
  "Done with this meeting"
- [x] 2.5 Screenshots at 1400 and 900 px wide (offscreen, invented data)

- [x] 2.8 Done items folded at the end of a list; Undo bar and Ctrl+Z after check off, discard
  and switch all (`snapshot`/`restore`); tests
- [x] 2.9 Switch all on / off in the send bar (`set_send_all`: open items only); test
- [x] 2.10 Keys in the item lists (↑↓ J/K, Home/End, Space, T, E/Enter, Delete, Ctrl+Z), the
  current item outlined; test
- [x] 2.11 The rail's Action items page (Ctrl+4): `open_items` across the library, a heading per
  meeting, a filter; tests
- [x] 2.13 The page's UI pass: meeting cards with date tile, people and tags; dense rows with chips
  and round edit / envelope / check / cross buttons; counts that filter; owner chips; scrolling
  measured without hover layout; light and dark screenshots; tests
- [x] 2.12 A note line starting with a time gets the passage around it in the summary request; test

## 3. Documents

- [x] 3.1 Guide, Studio roadmap, changelog, README
- [x] 3.2 `docs/studio.png` taken again with the 1.6.0 rail (offscreen, invented data)
