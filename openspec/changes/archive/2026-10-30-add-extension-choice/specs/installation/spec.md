## ADDED Requirements

### Requirement: Choosing extensions
`install.sh --with-studio` SHALL make an installed Echo load Echo Studio and `--without-studio`
SHALL stop it, the choice remembered across installs and removed by `uninstall.sh`. An installed
Echo SHALL load no extension it was not installed with. `echo-app doctor` SHALL name the loaded
extensions, or say there are none.

#### Scenario: Installed without Studio
- **WHEN** Echo was installed with `./install.sh` and Studio's package is in the clone
- **THEN** Echo starts without Studio, and `doctor` says "none (Echo alone)" with the flag to add it
