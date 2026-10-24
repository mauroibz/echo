# Proposal

## Why

The base model is multilingual; Echo hard-codes Spanish and always applies the Spanish
adapter. People who record in another language, or who mix Spanish and English, get a worse
transcript than the model could give.

## What Changes

- A language per recording, defaulting to a global setting (Spanish). The processor is told
  the language; the Surus adapter is applied only for Spanish.
- "Detect" as an option when the processor exposes language identification; otherwise the
  list of languages the model card supports.
- The transcript's `language` field reflects the request; search folding stays accent-insensitive.

## Capabilities

### Modified Capabilities
- `transcription`: language per recording, adapter only for Spanish.

## Impact

`worker/asr.py` (`language` parameter, adapter guard), `transcription.py` and `cli_tr.py`
(`--language`), `settings.py`, the transcript panel's request menu, the model-info key for
partial results.
