# Spec Delta

## Purpose
Defines how Echo is installed, updated and removed on a Linux machine without root access
or changes to the system Python, and how the install verifies itself.

## ADDED Requirements

### Requirement: Per-user installation
The installer SHALL install Echo using only the `uv` binary as a bootstrap dependency and
SHALL write only inside the repository clone and the user's home directory. It SHALL NOT
use, modify or install packages into the system Python interpreter.

#### Scenario: Fresh install
- **WHEN** a user with `uv`, PipeWire and ffmpeg runs the installer in a fresh clone
- **THEN** the `echo-app` command is available on the user's PATH and a desktop launcher
  named "Echo" appears in the application menu

#### Scenario: System Python untouched
- **WHEN** the install completes
- **THEN** no file under `/usr` has been created or modified and the interpreter used by
  Echo is a uv-managed CPython matching the version pinned in the repository

### Requirement: Reproducible dependencies
Installs SHALL resolve exactly the package versions and hashes recorded in the committed
lockfile, SHALL refuse source distributions, and SHALL fail if the lockfile is out of date
with the project definition.

#### Scenario: Lockfile drift
- **WHEN** the project dependencies are changed without regenerating the lockfile
- **THEN** the installer stops with an error naming the lockfile and does not install

### Requirement: Install profiles
The installer SHALL offer a base profile (recording, library, editor) and a full profile that
adds local transcription. The base profile SHALL NOT install GPU or machine-learning packages.

#### Scenario: Base profile
- **WHEN** the installer runs without the transcription option
- **THEN** recording and the library work, and transcription actions explain that the
  transcription components are not installed

### Requirement: Uninstall
The uninstaller SHALL remove launchers and desktop entries it created and SHALL leave the
user's recordings in place unless the user explicitly asks to delete them.

#### Scenario: Uninstall keeps data
- **WHEN** the user runs the uninstaller without the purge option
- **THEN** the launcher and desktop entry are gone and every recording folder still exists

### Requirement: Doctor self-check
`echo-app doctor` SHALL report pass, warn or fail for each prerequisite: PipeWire capture
tool, ffmpeg and the decoders needed for supported import formats, interpreter version,
lockfile sync, free disk space in the data directory, and, when the full profile is
installed, GPU visibility, Hugging Face credentials and presence of the pinned model
revisions. Each non-passing line SHALL state how to fix it. The command SHALL exit non-zero
when any check fails.

#### Scenario: Missing ffmpeg
- **WHEN** ffmpeg is not on PATH
- **THEN** doctor shows a failing ffmpeg line with the package to install and exits non-zero

#### Scenario: Healthy machine
- **WHEN** all prerequisites are present
- **THEN** every line passes and the exit status is zero
