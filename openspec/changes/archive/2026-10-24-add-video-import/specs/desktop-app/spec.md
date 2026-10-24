## MODIFIED Requirements

### Requirement: Drag and drop import
Dropping audio or video files, or folders, anywhere on the window SHALL import them, showing
progress (including progress within a file whose audio is being extracted) and a summary of
imported, duplicate and rejected files. The drop overlay SHALL read "Drop audio or video to
import" and the open dialog SHALL list audio and video files. Dropped web links that are not
local files SHALL be rejected with a message.

#### Scenario: Drop a WhatsApp note
- **WHEN** the user drops a `.opus` voice note on the window
- **THEN** it appears in the library, selected, and transcription starts if enabled

#### Scenario: Drop a meeting video
- **WHEN** the user drops an OBS screen recording on the window
- **THEN** it appears in the library as an audio recording, selected, and transcription starts if enabled
