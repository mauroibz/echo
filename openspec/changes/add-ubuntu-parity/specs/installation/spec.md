## MODIFIED Requirements

### Requirement: Doctor self-check
`echo-app doctor` (and Help → Check setup) SHALL check PipeWire tools and audio nodes, ffmpeg
and its decoders, the Python environment, the lockfile, disk space, the GPU, the Hugging Face
login and the model files, and the libraries the window needs on the current display server.
Every failed or warned check SHALL name a fix, and the fix SHALL use the package manager of the
running distribution (apt, dnf or pacman) when a system package is involved.

#### Scenario: PulseAudio still owns audio
- **WHEN** `pw-record` is installed but PipeWire exposes no audio nodes
- **THEN** doctor fails the audio check and explains that the session runs PulseAudio, how to
  switch to PipeWire on this distribution, and that Ubuntu 22.10 or newer has it by default

#### Scenario: Ubuntu on X11 without the cursor library
- **WHEN** the session is X11 and the Qt xcb cursor library is missing
- **THEN** doctor fails with `sudo apt install libxcb-cursor0`

## ADDED Requirements

### Requirement: Tested on more than one distribution
Every push SHALL run the fast test suite on an Ubuntu runner and in a Fedora container, and
SHALL resolve both install profiles from `uv.lock`. Releases SHALL be tagged and listed in a
changelog.

#### Scenario: Lockfile breaks a profile
- **WHEN** a dependency change makes the full profile unresolvable on one platform
- **THEN** the workflow fails before the change is released
