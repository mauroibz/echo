# transcription Specification

## Purpose
Produces a timed Spanish transcript for any recording in the library, in the background,
without blocking recording or editing and without losing progress or user edits.

## Requirements

### Requirement: Background queue
Transcription SHALL run in a separate background process. Recordings SHALL be transcribed one
at a time in the order they were queued. The user interface and recording SHALL remain fully
usable while transcription runs. The queue SHALL survive application restarts.

#### Scenario: Queue three recordings
- **WHEN** the user queues three recordings
- **THEN** they are transcribed one after another, each showing queued, then progress, then done

#### Scenario: Restart while queued
- **WHEN** the application is closed with recordings still queued and opened again
- **THEN** transcription of the queued recordings continues

### Requirement: Long-form audio
Echo SHALL transcribe recordings of any length that fits on disk. Audio SHALL be split at pauses
in speech into passages of at most 30 seconds. Stretches without speech SHALL be skipped. Each
passage of the transcript SHALL keep its start and end time in the recording, and pauses of
two seconds or more SHALL start a new paragraph.

#### Scenario: One-hour monologue
- **WHEN** a one-hour recording is transcribed
- **THEN** the transcript covers the whole recording as timed passages with paragraph breaks, and
  silent stretches produce no text

### Requirement: Crop respected
When a recording has crop points, only the audio between them SHALL be transcribed, and passage
times SHALL still refer to positions in the full recording.

#### Scenario: Cropped intro
- **WHEN** a recording is cropped to start at 1:00 and is transcribed
- **THEN** the first passage starts at or after 1:00

### Requirement: Progress and cancellation
While a recording is being transcribed, Echo SHALL show the fraction done and an estimate of the
time remaining, updated at least every ten seconds. The user SHALL be able to cancel a queued or
running transcription; cancelling SHALL stop work within a few seconds and leave any previous
transcript in place.

#### Scenario: Cancel running transcription
- **WHEN** the user cancels a transcription halfway through
- **THEN** the work stops, the progress indicator disappears, and the previous transcript (if any)
  is unchanged

### Requirement: Resumable work
If the worker stops during a transcription (crash, power loss, application closed), the next
run SHALL continue from the passages already transcribed rather than starting over, provided the
audio, crop and model settings are unchanged.

#### Scenario: Worker killed
- **WHEN** the worker is killed after transcribing half the passages of a recording
- **THEN** the next run transcribes only the remaining passages

### Requirement: Edits are never overwritten
The model transcript SHALL be stored separately from the user's edited text. Re-transcribing a
recording SHALL replace only the model transcript; the user's edits SHALL be kept and remain
what the user sees, and the user SHALL be told that a newer model transcript is available.

#### Scenario: Re-transcribe an edited recording
- **WHEN** the user re-transcribes a recording whose text they edited
- **THEN** their edited text is unchanged and they can choose to switch to the new model output

### Requirement: Model provenance
Each transcript SHALL record the model and adapter repositories and revisions used, whether the
adapter was enabled, the language, the creation time, and the context sentence given to the
model, if any.

#### Scenario: Inspect provenance
- **WHEN** a transcript is created with the adapter enabled and a dictionary context
- **THEN** its stored data names both revisions and the exact context sentence

### Requirement: Failures are reported, not silent
If a transcription fails, Echo SHALL record a human-readable reason on the recording, stop
retrying it automatically, and let the user retry. Running out of GPU memory SHALL be handled by
retrying with smaller batches before failing.

#### Scenario: Models not downloaded
- **WHEN** a transcription is requested and the model files are missing
- **THEN** the recording shows a failure explaining that the models must be downloaded, with the
  command or button to do it

### Requirement: GPU memory released when idle
The worker SHALL exit after the configured idle time (default five minutes) with no queued work,
releasing all GPU memory.

#### Scenario: Idle exit
- **WHEN** the queue has been empty for the idle timeout
- **THEN** no Echo process holds GPU memory

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

### Requirement: Language per recording
Each transcription SHALL use the recording's language, defaulting to the global setting, and
SHALL apply the Spanish adapter only when the language is Spanish. The available languages
SHALL be those the pinned model supports.

#### Scenario: English voice note
- **WHEN** the user sets a recording's language to English and transcribes it
- **THEN** the transcript is English, the adapter is recorded as not enabled, and the style sentence used is the English one
