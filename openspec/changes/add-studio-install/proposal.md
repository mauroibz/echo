# Installing Studio

## Why

Studio has to reach users without a branch switch, and Echo without Studio must stay exactly
Echo.

## What Changes

- Echo's installer chooses (`--with-studio` / `--without-studio`, in `add-extension-choice`,
  archived on main); `doctor` names the loaded extensions.
- The guide and README say how to install Studio and what it sends.
- Studio stays on the `studio` branch until it merges into `main` and ships with an Echo
  release; from then on one repository, one version, and the installer decides.

## Capabilities

### Modified Capabilities

None here: the installer's requirement is in `installation` (`add-extension-choice`).

## Impact

`docs/guide.md`, `README.md`, `docs/studio-roadmap.md`.
