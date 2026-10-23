# Design

## Context

Greenfield repository. Host tools available: uv, ffmpeg, PipeWire utilities. See proposal.md
for motivation and PLAN.md sections 2 and 9 for the agreed layout and packaging approach.

## Goals / Non-Goals

**Goals:**
- One package, `echo_app`, with a CLI entry point `echo-app` and stdlib-only core modules
  (paths, settings, library, index) so they import in milliseconds and carry no third-party risk.
- A doctor that is useful on day one and grows as later changes add checks.

**Non-Goals:**
- Packaging for other distributions (Flatpak, RPM). Not needed for a per-user install.
- Windows or macOS support.

## Decisions

- **uv project with `src/` layout, `python-preference = "only-managed"`, pinned 3.14.**
  The system interpreter is never selected. Alternative considered: pipx. Rejected because it
  cannot hash-lock the full tree.
- **Install profiles as an optional dependency group `worker`.** `uv sync --locked --no-build`
  for base, `--extra worker` for full. One lockfile covers both.
- **Install location is the clone itself (`.venv`)**, with symlinks in `~/.local/bin` and a
  desktop file in `~/.local/share/applications`. Updating is `git pull && ./install.sh`.
- **Settings as TOML** read with stdlib `tomllib` and written by a tiny serializer (flat
  keys, scalar values only). Alternative: JSON. TOML is easier to hand-edit with comments.
- **Index is SQLite in WAL mode** with `recordings` and `jobs` tables. The index stores only
  derived data; `rescan` reconstructs it from `meta.json` files. Schema version in
  `PRAGMA user_version`; on mismatch the index is dropped and rebuilt, which is safe because
  it holds nothing original. Job rows are the one exception: they are re-derived from
  "audio present, transcript absent" plus a marker file `transcribe.requested` in the
  recording folder, so a rebuilt index re-queues pending work.
- **Atomic writes** everywhere via write-to-temp, fsync, rename, fsync directory.
- **Trash** implements the freedesktop.org trash spec directly (move into
  `~/.local/share/Trash/files` plus a `.trashinfo` file) when the data directory is on the
  same filesystem as the home trash; otherwise moves to `<data>/trash/`. No dependency on
  `gio` or `kioclient`.
- **Recording ids**: `YYYY-MM-DDTHH-MM-SS_xxxx` with 4 random hex chars. Sortable, readable,
  collision-safe for a single user.

## Risks / Trade-offs

- [uv not installed on a new machine] → install.sh prints the one-line install command
  (`dnf install uv`) and exits.
- [SQLite index shared across machines through file sync could conflict] → out of scope for
  now; the index is rebuildable, so a conflict costs a rescan, not data.
