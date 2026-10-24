# Tasks

## 1. Distribution-aware fixes

- [ ] 1.1 Add `doctor.distro()` reading `/etc/os-release` (ID and ID_LIKE) and a `pkg_cmd(packages_by_family)` helper; route every existing fix string through it; unit test with sample os-release texts
- [ ] 1.2 Use the same helper in `install.sh` for the uv, ffmpeg and PipeWire hints

## 2. New checks

- [ ] 2.1 Audio nodes check: `pw-dump` succeeds but lists no `Audio/Source` or `Audio/Sink` → FAIL with the PulseAudio explanation; test with a captured empty dump
- [ ] 2.2 Display check: on X11 (`XDG_SESSION_TYPE`/`DISPLAY` without Wayland) verify `libxcb-cursor.so.0` loads via `ctypes.util.find_library`; FAIL with the apt/dnf/pacman fix
- [ ] 2.3 Move the README troubleshooting entries these replace into one line pointing at doctor

## 3. Continuous testing and releases

- [ ] 3.1 `.github/workflows/test.yml`: matrix of `ubuntu-latest` and `fedora:latest` container; install uv, `uv sync --locked --no-dev`, `uv sync --locked --extra worker --dry-run` (resolution only, no 3.5 GB download), `uv run --no-sync pytest`
- [ ] 3.2 `CHANGELOG.md` with the current state as 0.1.0; tag `v0.1.0`; README update section uses `git fetch --tags && git checkout $(git describe --tags --abbrev=0)`
- [ ] 3.3 Verify on a real Ubuntu 24.04 VM: install, doctor, record, import; and on 22.04 confirm the PulseAudio message appears (needs hardware: Ubuntu VMs)
