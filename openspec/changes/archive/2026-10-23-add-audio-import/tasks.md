# Tasks

## 1. Importer

- [x] 1.1 Implement title/date derivation for WhatsApp and generic names; verify with unit tests covering PTT-, AUD-, "WhatsApp Audio ... at ..." and plain names
- [x] 1.2 Implement probe, staged verified copy, duplicate detection and batch results (imported, duplicate, rejected); verify with tests on generated Opus, M4A, AMR (if decodable), MP3, WAV and a non-audio file
- [x] 1.3 Clean stale staging files at start and verify an interrupted copy leaves no recording (test kills a copy mid-way)
- [x] 1.4 Add `auto_transcribe` setting and queueing on import and on recording finalize; verify markers are written only when transcription is installed and the setting is on

## 2. CLI

- [x] 2.1 Add `echo-app import PATH...` with per-file results and a non-zero exit when nothing was imported; verify by running it on a folder of mixed files
