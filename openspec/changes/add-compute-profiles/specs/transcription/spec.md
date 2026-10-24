## ADDED Requirements

### Requirement: Runs on the installed device with stated speed
Transcription SHALL run on the device of the installed profile (CUDA, ROCm or CPU) with the
same model, adapter, passage planning and output format. On CPU the engine SHALL use the
fastest configuration whose output agrees with the GPU configuration on reference recordings
at 99% of words or better. Echo SHALL tell the user the expected transcription speed on this
computer, measured from completed jobs, before they queue long recordings.

#### Scenario: First transcription on CPU
- **WHEN** a 10-minute recording is transcribed on the `cpu` profile
- **THEN** it completes with the same passage structure as on GPU, and afterwards the welcome
  screen and doctor show the measured minutes per hour of audio
