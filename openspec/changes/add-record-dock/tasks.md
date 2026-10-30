# Tasks

- [x] 1.1 `ui/record_dock.py`: rest, recording, paused, saved and minimal states; level wave on the motion clock; problems; drag with `startSystemMove`; tests offscreen
- [x] 1.2 Window: Ctrl+Shift+D action, closing while recording shows the dock, Open selects the recording, position in the UI state; recorder: marker without the note field, marker count; tests
- [ ] 1.3 Check always-on-top on this machine's KDE Plasma Wayland session; write what was seen in `design.md` (needs a person at the desktop)

## Blocked

- **1.3** An agent could not drive the real desktop here (showing a window on the user's
  session and asking KWin about it was not allowed). To check: start Echo, press Ctrl+Shift+D,
  click another window (a browser) so it comes to the front, and look whether the dock stays
  visible above it. Then drag the dock somewhere else, press Ctrl+Shift+D twice, and see whether
  it comes back in the same place (on Wayland the compositor decides; on X11 it should). Write
  both results in `design.md` under Decisions, and if KDE does not keep it above, say so in the
  guide's sentence about GNOME.
- [x] 1.4 `docs/guide.md`, `docs/design.md`, `CHANGELOG.md`, `docs/roadmap.md`
