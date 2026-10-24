# Design

## Decisions

- **Global shortcuts.** Through the XDG Desktop Portal `org.freedesktop.portal.GlobalShortcuts`
  (KDE Plasma 6 and GNOME 46+ implement it) using `QtDBus` from PySide6-Essentials: on start,
  `CreateSession`, then `BindShortcuts` for two actions, `record-toggle` and `quick-note`, with
  suggested triggers `Ctrl+Alt+R` and `Ctrl+Alt+N`; the portal shows its own dialog the first
  time and remembers. If the portal is absent (no interface on the session bus), the Settings
  page shows "Your desktop has no global shortcuts portal. Bind a key to `echo-app record
  --toggle` and `echo-app record --quick-note` in its keyboard settings." The window must be
  running (possibly in the tray) for the portal route; the CLI route works regardless.
- **CLI.** `echo-app record --toggle` starts a recording or stops the active one;
  `--quick-note` starts one with `quick_note: true` and tag `nota` in `meta.json`, and if one
  is active, stops it.
- **Delivery.** When a transcript finishes for a recording with `quick_note` and the window
  is running, the window copies the text to the clipboard and shows a tray notification
  ("Nota lista, copiada al portapapeles", 5 s); then clears `quick_note` so it happens once.
  Without the window (CLI only), `echo-app record --quick-note --wait` waits and prints the
  text to stdout, which a user can pipe to `wl-copy`.
- **Auto title.** `Meta.title_auto: bool` is True for recordings whose title was generated
  (timestamp titles), False for imports and for anything renamed. When a transcript finishes
  and `title_auto` is True, the title becomes the first sentence of the text (cut at the
  first sentence end or 60 characters, whichever is first, trailing punctuation removed).
  Renaming sets `title_auto` False. The list and the index update through the existing change
  path.

## Decisions made while implementing

- **D-Bus through `jeepney`**: PySide6's QtDBus aborts the process inside libdbus when building
  the `a(sa{sv})` argument of `BindShortcuts` (tried; the abort is libdbus's type check). jeepney
  is pure Python with no dependencies, Linux-only in `pyproject.toml`. The portal session must
  outlive the call, so one thread keeps the connection and listens for `Activated`.
- **Messages in English**, like the rest of the interface ("Note ready and copied to the
  clipboard: …"), not the design's Spanish example.
- **The toggle stops "what it started"**: `--toggle` and `--quick-note` both stop whatever
  recording is active.
- **Auto titles** are set by the worker when the transcript is written, so CLI-only use gets them
  too; renaming in the window sets `title_auto` false for good. Imports keep their file-derived
  titles.
- **Delivery** in the window listens to the list model's changed recordings; the flag is cleared
  after the first delivery, so re-transcribing does not copy again.
- **Setting** `global_shortcuts` (on) turns the portal off when unchecked; tests never touch the
  real desktop (`ECHO_NO_PORTAL`).
- **End to end** with the real model: a capture command "speaking" a synthesized sentence, then
  `echo-app record --quick-note` twice with `--wait`: the text was printed 4.9 s after stopping,
  the title became its first sentence and the recording was tagged `nota`.
