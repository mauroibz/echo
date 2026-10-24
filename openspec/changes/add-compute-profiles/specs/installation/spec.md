## MODIFIED Requirements

### Requirement: Install profiles
The installer SHALL offer a base profile (record, import, play, edit) and three mutually
exclusive transcription profiles: `cuda` for NVIDIA GPUs, `cpu` for any x86-64 or arm64
processor, and `rocm` for AMD GPUs on Linux. `--with-transcription` without a value SHALL pick
the profile matching the detected hardware and say so. All profiles SHALL come from the single
hash-locked `uv.lock` as prebuilt wheels. The profile SHALL be remembered for updates, and
`doctor` SHALL report it and whether the hardware matches.

#### Scenario: Laptop without a GPU
- **WHEN** the user runs `./install.sh --with-transcription` on a machine with no NVIDIA or AMD GPU
- **THEN** the `cpu` profile is installed, about 200 MB of torch is downloaded, and the
  installer says transcription will run on the processor

#### Scenario: Wrong profile for the hardware
- **WHEN** the `cuda` profile is installed and no NVIDIA driver is present
- **THEN** doctor warns and suggests `./install.sh --with-transcription=cpu`
