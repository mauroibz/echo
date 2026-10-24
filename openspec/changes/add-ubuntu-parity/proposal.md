# Proposal

## Why

Echo's README promises Ubuntu, Debian and Arch, but the installer and `doctor` only know how
to fix things on Fedora (`sudo dnf install ...`), the known Ubuntu X11 failure (`libxcb-cursor0`)
is a README footnote instead of a check, and Ubuntu 22.04 LTS still routes audio through
PulseAudio, so `pw-record` finds no inputs and Echo gives no explanation. Nothing runs the test
suite on any distribution but the author's machine.

## What Changes

- `doctor` and `install.sh` detect the package manager from `/etc/os-release` and print the
  apt, dnf or pacman command for every fix.
- New checks: the Qt xcb cursor library on X11 sessions; "PipeWire installed but no audio
  nodes" (PulseAudio still owns audio), with the fix for Ubuntu 22.04 and a pointer to 22.10+.
- A GitHub Actions workflow runs the fast suite (`uv run --no-sync pytest`) on `ubuntu-latest`
  and in a Fedora container on every push, and resolves both install profiles from the lockfile.
- Tagged releases: `CHANGELOG.md`, a `v0.x` tag per release, and the README update step says
  `git pull` to the latest tag.

## Capabilities

### Modified Capabilities
- `installation`: distribution-aware fixes, two more doctor checks, continuous testing, versions.

## Impact

`doctor.py`, `install.sh`, README, new `.github/workflows/test.yml`, `CHANGELOG.md`. No
behavior change on Fedora except the wording of fixes.
