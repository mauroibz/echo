## MODIFIED Requirements

### Requirement: Originals are never altered
Echo SHALL NOT modify or delete an original audio file except when the user deletes the
recording. For a recording imported from a video, the original is the extracted audio file;
Echo SHALL NOT keep, modify or delete the video, and SHALL record the video's name, size and
hash in `meta.json`. Crop SHALL be stored as in and out points, and exporting a cropped version
SHALL write a new file.

#### Scenario: Crop does not touch audio
- **WHEN** the user sets crop points on a recording
- **THEN** the original audio file's bytes and hash are unchanged

#### Scenario: Deleting a recording made from a video
- **WHEN** the user deletes a recording imported from a screen recording
- **THEN** the recording folder goes to the trash and the video file is untouched
