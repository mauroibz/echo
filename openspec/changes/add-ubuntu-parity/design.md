# Design

## Decisions

- **Distribution detection.** `doctor.distro() -> str` returns one of `fedora`, `debian`,
  `arch`, `other` from `/etc/os-release` `ID`, then `ID_LIKE` (so Ubuntu, Mint and Pop map to
  `debian`; Nobara and Bazzite to `fedora`; Manjaro and EndeavourOS to `arch`). `pkg_cmd(
  {"fedora": "pipewire-utils", "debian": "pipewire-bin", "arch": "pipewire"})` renders
  `sudo dnf install …`, `sudo apt install …` or `sudo pacman -S …`; for `other` it lists the
  package names with "install with your package manager".
- **Audio-nodes check.** `pipewire.list_sources()` empty while `pw-dump` succeeds → FAIL
  "PipeWire is installed but not running the audio session (PulseAudio still owns audio)" with
  the fix `sudo apt install pipewire-audio-client-libraries wireplumber && systemctl --user
  --now enable wireplumber pipewire-pulse` on `debian`, and the note that Ubuntu 22.10 or newer
  needs nothing.
- **Display check.** Only when `XDG_SESSION_TYPE == "x11"` or `DISPLAY` is set without
  `WAYLAND_DISPLAY`: `ctypes.util.find_library("xcb-cursor")` is None → FAIL with the package
  `libxcb-cursor0` / `xcb-util-cursor` / `xcb-util-cursor`.
- **CI.** `.github/workflows/test.yml`, trigger on push and pull request. Jobs: `ubuntu`
  (`ubuntu-latest`, `apt-get install -y ffmpeg libegl1 libgl1 libxkbcommon0 libfontconfig1
  libdbus-1-3 libxcb-cursor0`, `astral-sh/setup-uv`) and `fedora` (`container: fedora:latest`,
  `dnf install -y ffmpeg-free mesa-libEGL mesa-libGL libxkbcommon fontconfig dbus-libs
  xcb-util-cursor`, uv from the install script). Steps in both: `uv sync --locked
  --no-install-project`, `uv lock --check`, `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest
  -q`, and `uv sync --locked --extra worker --dry-run` to prove the full profile resolves
  without downloading torch (if `--dry-run` is not supported by the pinned uv, use
  `uv export --locked --extra worker > /dev/null`).
- **Releases.** `CHANGELOG.md` in Keep-a-Changelog form with an `Unreleased` section and
  `0.1.0` for the current state. Tags `vX.Y.Z`. README update text:
  `git fetch --tags && git checkout "$(git describe --tags --abbrev=0 origin/main)" && ./install.sh`.

## Decisions made while implementing

- **Python install step.** Fedora's packaged `uv` sets Python downloads to manual, so
  `uv sync` alone fails with "No interpreter found for Python 3.14 in managed installations"
  (found by running the Fedora job in a container). `install.sh` and both CI jobs now run
  `uv python install` with the pinned version first, which works with either setting. The
  README's `sudo dnf install uv` instruction was broken before this.
- **`uv` hint.** Fedora and Arch package `uv`; Ubuntu and Debian do not, so their hint is the
  official install script.
- **Audio-nodes check when PipeWire is not running at all** (pw-dump fails): FAIL with
  `systemctl --user --now enable pipewire wireplumber`.
- **GPU driver fix** is per family too (`ubuntu-drivers install`, `pacman -S nvidia`,
  RPM Fusion's `akmod-nvidia`).
- **CI verification.** Both jobs were run locally with podman in `ubuntu:24.04` and
  `fedora:latest`, including `./install.sh`; the workflow itself has not run on GitHub,
  because this work stays local until it is pushed.
