# Tasks

The reference recording is the meeting video the user chose: a 40-minute OBS `.mp4` in
`~/Videos` (H.264 + one AAC 48 kHz stereo track, about 1 GB, several Spanish speakers). Its file
name names the people in it, so it is not written into the repository; ask in the session if it
is not given. Nothing from it (audio, transcript, names) goes into the repository or its tests.

## 1. Extraction

- [ ] 1.1 `ffmpeg.probe` reports whether the file has a real video stream (attached pictures excluded) and the index, codec, duration and default flag of every audio track; existing callers unchanged; tests with ffmpeg-generated files (an `.m4a` with cover art is not a video)
- [ ] 1.2 `ffmpeg.extract_audio(src, track, dest, progress)` following the table in the design, with `-progress pipe:1` reporting a fraction; tests generating short videos with `lavfi` (`testsrc` + `sine`) in AAC, Opus, MP3, PCM and AC3, checking the stored extension and codec
- [ ] 1.3 Verification: streamhash comparison for copies, full decode and length check for encodes; a test that corrupts the extracted file before verification and expects a rejection and no recording

## 2. Import

- [ ] 2.1 `importer.import_file` takes the video path: hash the video, duplicate check against `sha256` and `extracted_from.sha256`, extract into staging, verify, rename into the recording, `extracted_from` in `meta.json`; "no sound" rejection; tests including a kill during extraction (staging file left, no recording, `clean_staging` removes it)
- [ ] 2.2 `VIDEO_EXTENSIONS` and `EXTENSIONS`; folder search, `watch.py` and the file dialog use `EXTENSIONS`; watched-folder test with a video appearing in the folder
- [ ] 2.3 OBS file names in `title_and_date`; tests
- [ ] 2.4 Fractional progress through `import_paths` and `echo-app import` (a line per file, the fraction on a TTY)

## 3. Window

- [ ] 3.1 Drop overlay text, open-dialog filter "Audio and video", progress within a file in the import dialog; UI test dropping a generated video offscreen
- [ ] 3.2 Drop the reference meeting video on the running window on this machine: record in `docs/design.md` the time from drop to the recording appearing, the stored size, and that the video's hash is unchanged; then transcribe it on the GPU and record the transcription time and the number of speakers found (needs hardware: the GPU and the reference video)

## 4. Finish

- [ ] 4.1 README (importing screen recordings, OBS's output folder as a watched folder), `docs/design.md` Import section (video, the format table, verification, `extracted_from`) and the storage tree, CHANGELOG
- [ ] 4.2 Fast suite passes; archive the change
