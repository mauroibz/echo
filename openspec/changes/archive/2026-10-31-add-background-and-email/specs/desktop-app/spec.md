## ADDED Requirements

### Requirement: Running in the tray
With "Keep Echo running in the tray, and start it when you log in" on, closing the window SHALL
leave Echo running in the tray, and an autostart entry SHALL start Echo at login without its
window. Turning it off SHALL remove the entry. `echo-app gui --background` SHALL start Echo in
the tray; when Echo is already running it SHALL leave it as it is.

#### Scenario: Ready for the first meeting
- **WHEN** the setting is on and the user logs in
- **THEN** Echo runs in the tray without opening its window, and closing the window later leaves it there
