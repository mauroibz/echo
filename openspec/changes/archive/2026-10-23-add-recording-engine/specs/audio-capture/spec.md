# Spec Delta

## Purpose
Captures audio from a chosen input into the library with the guarantee that no captured audio
is lost, whatever happens to the application, the device or the machine.

## ADDED Requirements

### Requirement: Source selection
Echo SHALL list available capture sources with human-readable names, grouped as inputs
(microphones and virtual sources) and output monitors (audio the computer is playing). The
system default input SHALL be preselected unless the user chose another source, and the user's
choice SHALL be remembered.

#### Scenario: Default preselected
- **WHEN** the user has never chosen a source
- **THEN** the system default input is selected and labeled as the default

#### Scenario: Remembered source missing
- **WHEN** the remembered source is not present (for example, a USB microphone is unplugged)
- **THEN** the default input is selected and the user is told the remembered source is unavailable

### Requirement: Input level monitoring
Echo SHALL show a live peak level of the selected source, updating at least ten times per
second, both before and during recording, and SHALL indicate clipping. The user SHALL be able
to listen to the selected input through the current output device, and listening SHALL be off
by default.

#### Scenario: Checking the microphone
- **WHEN** the user selects a source while not recording
- **THEN** the level meter moves with the input within half a second

### Requirement: Recording lifecycle
The user SHALL be able to start, pause, resume and stop a recording. Elapsed recorded time
SHALL exclude paused time. Only one recording SHALL be active at a time.

#### Scenario: Pause and resume
- **WHEN** the user records 10 s, pauses for 5 s, resumes, records 10 s and stops
- **THEN** the finished recording is about 20 s long and the pause is noted in its metadata

#### Scenario: Second recording refused
- **WHEN** a recording is active and another start is requested
- **THEN** the request is refused with a message naming the active recording

### Requirement: Recording independent of the window
Capture SHALL run in a process separate from the user interface. Closing or crashing the user
interface SHALL NOT stop or interrupt a recording.

#### Scenario: Window crashes while recording
- **WHEN** the user interface process is killed during a recording
- **THEN** capture continues, and the next time the window opens it shows the recording in
  progress with correct elapsed time and the ability to stop it

### Requirement: No audio lost
Captured audio SHALL be written to disk continuously and flushed to stable storage at least
every two seconds. If the recorder process is killed, all audio written before the kill SHALL
be recovered. After power loss, all audio flushed before the loss SHALL be recovered. The
finished file SHALL be lossless and SHALL be verified to decode to exactly the captured
samples before the raw capture files are removed.

#### Scenario: Recorder killed
- **WHEN** the recorder process and the capture process are killed with SIGKILL during recording
- **THEN** on next start the recording is finalized automatically, marked as recovered, and
  contains the audio captured up to the kill

#### Scenario: Verification fails
- **WHEN** the encoded file does not decode to the captured samples
- **THEN** the raw capture files are kept, the recording is marked as needing attention, and
  the user can retry finalizing

### Requirement: Capture interruptions
If capture stops unexpectedly or stalls for more than three seconds, Echo SHALL restart capture
into a new segment within two seconds, and SHALL fall back to the system default input if the
selected source cannot be opened after three attempts. Every interruption SHALL be recorded in
the recording's metadata with its time and cause and SHALL be visible to the user.

#### Scenario: Microphone unplugged
- **WHEN** the selected USB microphone is unplugged during recording
- **THEN** recording continues from the default input, and the recording shows a gap note with
  the time of the switch

### Requirement: Disk space guard
Echo SHALL refuse to start recording with less than 1 GB free in the data directory and SHALL
warn when less than ten minutes of recording space remains. When space runs out, Echo SHALL
stop and finalize the recording cleanly.

#### Scenario: Low disk at start
- **WHEN** the data directory has 500 MB free and the user presses record
- **THEN** recording does not start and the message states the free space and the minimum

### Requirement: Empty recordings discarded
A recording stopped with no captured audio SHALL be removed instead of being added to the library.

#### Scenario: Immediate stop
- **WHEN** the user starts and stops before any audio is captured
- **THEN** no recording appears in the library
