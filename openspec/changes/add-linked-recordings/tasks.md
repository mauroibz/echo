# Tasks

## 1. Sets on disk

- [x] 1.1 `sets.py`: read, create, extend, reorder, remove a member, dissolve; one set per recording with "newest file wins" on conflicting claims; atomic writes; tests including a missing member coming back and two files claiming one recording
- [x] 1.2 Index schema 3 with a `sets` table rebuilt from the files; `rescan` removes set files with no present members; migration test on a schema 2 index
- [x] 1.3 Auto title for sets (first part's first sentence until renamed), set by the worker path that sets recording auto titles; tests
- [x] 1.4 CLI: `echo-app link`, `unlink`, sets in `list`, set ids in `export`; tests

## 2. The list

- [ ] 2.1 Set and part rows in `LibraryModel` (placement by newest part, expansion kept in `UiState`, summary status, total cropped length) and their painting in `RowDelegate`; search and tag filters show a set with its matching parts; UI tests
- [ ] 2.2 Extended selection with the bottom bar ("N selected · Link · Delete…") and Ctrl+L; the current item still drives the panels; UI tests
- [ ] 2.3 Drag and drop in the list: onto a row links, onto a set appends, between parts inserts or reorders, between top-level rows takes a part out; visible drop indicator; Alt+Shift+Up and Down; UI tests driving real drags offscreen
- [ ] 2.4 Context menu "Remove from set" and "Unlink"; Delete on a set asks Unlink (default) or move all parts to the trash; UI tests

## 3. Reading and editing a set

- [ ] 3.1 Part map in the transcript panel; heading blocks with title, date and length, clicking the title selects the part; parts without text show their state; set header with title, part count, span, and a context line written to every part
- [ ] 3.2 Editing in place: key filter refusing edits in or across headings (typing, paste, cut, delete, backspace, drag of text); autosave splitting by headings and saving only changed parts; tests at every boundary
- [ ] 3.3 Find (and the carried-over library search), passage times, follow-along, low-confidence shading, dictionary underlines and chips, Ctrl+. and passage steps through the part map; tests
- [ ] 3.4 Copy and export of a set (text and Markdown with part headings; SRT, VTT, JSON on the set timeline); vault export as one note per set; tests

## 4. Playing a set

- [ ] 4.1 Player timeline of parts: hand-over to the next part at the end, seeking across parts, speed kept across parts; tests with the fake output
- [ ] 4.2 Waveform of concatenated cached peaks with part dividers and numbers; markers shown at set time; crop handles hidden in the set view; UI tests
- [ ] 4.3 Listen to a three-part set of real voice notes on this machine through PipeWire and check the hand-overs, seeking into the third part and follow-along (needs hardware: speakers or headphones and a person listening)

## 5. Burst offers

- [ ] 5.1 `sets.bursts()` with the rules in the design; tests on real WhatsApp file names (Android and desktop exports, numbering gaps, notes far apart, notes already in a set)
- [ ] 5.2 Banner above the list after imports and watched-folder imports, "Link them" / "Add to <set>" / dismiss remembered in `UiState`, "1 of N" for several offers; UI tests

## 6. Finish

- [ ] 6.1 README (linking, the banner, shortcuts, the set view), `docs/design.md` (set files and why not in `meta.json`, the part map), `docs/sync.md` (the `sets/` folder), Help → Keyboard shortcuts, CHANGELOG
- [ ] 6.2 Copy test on a copy of the real library: index migrates to schema 3, existing recordings untouched, a set of real voice notes created, edited, played and exported
