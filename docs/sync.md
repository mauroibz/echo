# Keeping Echo's files elsewhere

Everything Echo knows is in plain files, so backing it up or using it on two computers needs no
special feature. This page says what to copy and what to leave out.

## What is where

| What | Where (Linux) | Where (Windows) |
|---|---|---|
| Recordings, transcripts, tags, markers | `~/.local/share/echo/recordings/` | `Documents\Echo\recordings\` |
| Linked sets (which recordings belong together, in order) | `~/.local/share/echo/sets/` | `Documents\Echo\sets\` |
| People's profiles (notes, tags) | `~/.local/share/echo/people/` | `Documents\Echo\people\` |
| The search index | `library.sqlite` next to `recordings/` | the same |
| Settings | `~/.config/echo/settings.toml` | `%APPDATA%\Echo\settings.toml` |
| Dictionary of names and terms | `~/.config/echo/glossary.toml` | `%APPDATA%\Echo\glossary.toml` |
| Learned voices | `~/.config/echo/voices.json` | `%APPDATA%\Echo\voices.json` |

Each recording is one folder: its audio, `meta.json`, and its transcripts. Copying the folder is
enough to move a recording. A linked set is one small file in `sets/` naming its recordings; a
set whose recordings are not all there yet shows the ones that are, and the others rejoin it
when they arrive. If a set is changed on two computers at once, the newer file wins. A person's
profile is one small file in `people/`, so editing different people on two computers never
conflicts.

## Backups and sync

- **A backup** is a copy of the data folder (and, if you want your settings, dictionary and learned
  voices, of the settings folder). Any backup tool works; nothing needs Echo to be closed, although a
  recording in progress is only complete once it is stopped.
- **Syncing between computers** with Syncthing, Nextcloud or a shared drive works the same way.
  Exclude `library.sqlite`, `library.sqlite-wal` and `library.sqlite-shm`: the index is a cache
  that each computer rebuilds from the folders, and a database file changing under it can be
  damaged by a sync tool.
- **Do not record on two computers into the same synced folder at the same time.** The lock
  that allows one recording at a time works per computer.
- **Pointing Echo at the synced copy**: Settings → Recordings folder, or `data_dir` in
  `settings.toml`. Echo uses the new folder from its next start.
- **After a sync tool restores or adds folders** while Echo was closed, Echo picks them up on
  start. To rebuild the search index by hand: `echo-app rescan`.

## Notes in a Markdown vault

File → Export library to folder… (or `echo-app export --all FOLDER`) writes one Markdown note
per recording: title, date, length, tags, the people from the dictionary named in it, the note
you wrote, markers as headings, the text, and a link to the audio (or a copy of it). Notes that
are already up to date are not rewritten, so an Obsidian vault or any notes folder can hold them.

With "Keep this folder up to date while Echo runs", a recording's note is rewritten a couple of
seconds after you edit its transcript, title, tags, markers or notes. Echo only ever writes
outside its own folder there, and only replaces or removes notes it wrote and nobody changed
since: once you edit a note, it is yours and Echo stops updating it, and a file of yours with the
same name as a note gets a numbered name instead. To keep a note in sync, edit the transcript in
Echo rather than the note.
