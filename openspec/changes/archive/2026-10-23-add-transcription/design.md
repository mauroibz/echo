# Design

## Context

Verified on the target machine (RTX 3080 10 GB): the base model loads natively in transformers
5.19 (`CohereAsrForConditionalGeneration`) from the pinned revision in bf16 using 4.1 GB, the
PEFT adapter applies on top, and `disable_adapter()` switches it off per call. The stock
feature extractor imports librosa only to build its mel filterbank; transformers'
`mel_filter_bank(norm="slaney", mel_scale="slaney")` produces the same matrix to within
4e-9, so a subclass avoids librosa. silero-vad (torch JIT, CPU) processes 20 minutes of
audio in 8 s. The decoder prompt has a context slot (between `<|startofcontext|>` and
`<|startoftranscript|>`); putting known terms there corrected "Zurus" to "Surus" in a test.

## Goals / Non-Goals

**Goals:**
- Hours of audio with bounded memory and visible progress.
- The worker is the only process that imports torch.

**Non-Goals:**
- Knowledge-base correction and context biasing in the UI (later change; the transcriber
  accepts a context string internally so it can be added without rework).
- Speaker diarization (the model does not support it).
- Streaming or live transcription while recording.

## Decisions

### Process model and queue

`echo-app _worker --data-dir D` holds `D/.worker.lock` (flock) for its lifetime, so at most one
runs. The UI and CLI call `ensure_worker()` after queueing: if the lock is free, spawn the worker
detached. The queue is the set of recording folders containing `transcribe.requested`, ordered
by the timestamp inside it. The worker rescans every 2 s and exits after `worker_idle_minutes`
without work.

### Pipeline per recording

1. **Decode** the crop span with ffmpeg to 16 kHz mono int16 in memory (an hour is 115 MB).
2. **Speech detection**: silero-vad `get_speech_timestamps` (min silence 300 ms, pad 100 ms)
   with its progress callback feeding the progress file.
3. **Passage planning** (pure Python, unit-tested): walk speech regions; a passage may span at
   most 28 s; among the region boundaries that keep it within limits, cut at the widest pause,
   preferring passages of at least 8 s. A single speech region longer than 28 s is cut at the
   quietest 100 ms frame in its last 5 s. Pauses of 2 s or more between passages mark paragraph
   starts.
4. **Recognition** in batches sorted by length (default 8 passages); `max_new_tokens` scales
   with passage length. On CUDA out-of-memory the batch is halved and retried, down to 1, before
   failing. CPU fallback runs float32 with batch 1.
5. **Persistence**: after each batch, results are appended to `transcript.partial.json`
   (with a key of audio hash, crop, adapter flag and model revisions). On restart, a partial
   with a matching key is reused. When done, `transcript.json` is written atomically and the
   marker, progress and partial files are removed.

### Style primer and the short-output safety net

Measured on two audiobook chapters (20 and 32 minutes): without context the model wrote 5 of 63
and 48 of 102 passages in an unpunctuated lower-case style, and truncated one 10 s passage to
three words. The same happened through transformers' own long-form path, so it is model
behavior, not a pipeline artifact. A fixed sentence in the context slot ("El texto que sigue
está escrito en español correcto, con mayúsculas, tildes y signos de puntuación.") brought this
to 0 of 63 and 1 of 102 while keeping 99.8% word agreement on clean passages. Of five primers
tried, this one fixed the most passages and produced the shortest output on pure noise (the model
hallucinates on noise regardless; without any primer it invents whole sentences).

Context can also make the model stop early. Any passage whose output has fewer words than a
conservative floor for its length (0.4 words per second) is retried with the primer alone, then
with no context, keeping the fullest text. In the two chapters this recovered one passage
(5 to 31 words). Caller context (future knowledge base) goes before the primer: with terms
after it, one test clip came back empty.

### Measured throughput

RTX 3080: 20 min of audio in 18 s and 32 min in 23 s, including 3 s of model loading, about
70x real time. Resume after a kill reuses speech detection and finished passages.

### Progress

`transcribe.progress.json` holds `{stage, done, total, eta_s, started}` where stage is
`loading`, `detecting` or `transcribing`; ETA is from measured throughput of completed batches.

### Cancellation

The worker re-reads the marker before each batch; if it vanished (UI deleted it) or its
`requested` timestamp changed (re-queued with new options), it abandons the current job,
removing the partial if cancelled.

### Transcript format

```json
{"version": 1, "language": "es", "created": "...",
 "model": {"base": "repo@rev", "adapter": "repo@rev", "adapter_enabled": true},
 "audio_sha256": "...", "crop": [start, end],
 "segments": [{"start": 0.8, "end": 27.9, "text": "...", "paragraph": true}],
 "text": "joined text, blank line between paragraphs"}
```

### Edited text

Unchanged from library-storage: `transcript.edited.txt` wins when present. When a new
`transcript.json` is newer than the edited file, the UI offers to switch to it.

## Risks / Trade-offs

- [Passage boundaries split sentences, giving stray capitals or periods] → cut at the widest
  pauses and use long passages; a later correction pass can smooth joins.
- [transformers internals change across versions] → the feature extractor subclass depends on
  attribute names; versions are locked and a smoke test transcribes a known clip.
- [silero-vad misses very quiet speech] → padding and a low threshold; passages are formed from
  regions, so short false negatives inside a passage are still transcribed.
