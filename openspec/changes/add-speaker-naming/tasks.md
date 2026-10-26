# Tasks

## 1. Worker

- [x] 1.1 `settings.your_name`; the speakers record gains `tracks` (calls) and `me`; the worker names the user in `meta.json` (the one microphone-track speaker of a call, else the speaker suggested as the user), never over a name the user gave, and folds the voice only under the call rule; tests with the stub embedder: a call with and without a learned voice, a plain recording with the voice learned, a speaker already named, no `your_name`

## 2. The naming bar

- [x] 2.1 The bar above the transcript: one unnamed speaker at a time, most speech first; a known voice offers "Yes, NAME" and "Someone else…"; otherwise a name field with the dictionary's people (Enter names); "It's me" (asks for your name inline the first time, saves it, remembers the voice); ▶ plays 6 s of the speaker's longest passage; "Not now" sets `naming_dismissed`; no focus taken; hidden for sets, while the dictionary chip shows, and when everyone is named; offscreen tests for each
- [x] 2.2 "Your name" in Settings, renaming the voice entry when it changes; offscreen test

## 3. Docs

- [x] 3.1 README (naming speakers, your name, where voices are kept), `docs/design.md` (speakers section), CHANGELOG

## 4. With real recordings

- [ ] 4.1 Name yourself in one real recording, then transcribe two more of your own (one a call, one not) (needs the speaker model and real recordings): you are named in both without a question, and nobody else is named you

## Blocked

- **4.1** needs the user's own voice in real recordings, transcribed with the speaker model;
  running it on the user's library would rename speakers in it, so it was left to them.
  Everything else runs in the fast suite with a stub embedder. To check:
  open one of your recordings with speakers, answer "It's me" for your voice (give your name if
  asked); then record or import one call made with "Computer audio" and one recording that is
  not a call, both with you and someone else, and let them transcribe. Look for: your name beside
  your passages in both without the bar asking about you; nobody else carries your name; the bar
  asks about the other person, offering a name only if you named them before. If someone else is
  named you, note the two voices' similarity (`echo-app info <id> --json`, then the centroids in
  `transcript.json`) in `design.md`.

