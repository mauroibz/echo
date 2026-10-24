# Design

## Decisions

- **Supported languages.** Read from the pinned base model's tokenizer: the language tokens
  are the special tokens of the form `<|xx|>` in `tokenizer.json`'s `added_tokens`.
  `models.supported_languages()` parses that file (cached, no torch) and returns the two-letter
  codes; the UI shows names from a small code→name table in `models.py` (Spanish, English,
  Portuguese, French, Italian, German, Catalan, and any other code as its code). Verify at
  implementation that the processor accepts `language=` for each listed code; drop codes it
  rejects and record which in this file.
- **Style sentence per language.** `asr.STYLE_CONTEXT` becomes a dict: Spanish keeps the
  existing sentence; English gets "The following text is written in correct English, with
  capital letters and punctuation."; other languages use no style sentence (the dictionary
  sentence still applies). Record on a 1-minute clip per language that the sentence does not
  reduce word count, as the smoke test does for Spanish.
- **Adapter rule.** `adapter and language == "es"`; `model_info()` reports
  `adapter_enabled` accordingly, so provenance and the partial-results key stay correct.
- **Where the language lives.** `meta.json` `language: str | None` (None = use the default);
  `settings.language: str = "es"`; the request stores the resolved code; `transcript.json`
  `language` is the resolved code. The transcript panel's transcribe menu gets "Language ▸"
  with the list and "Default (Spanish)"; Settings gets "Transcription language".
- **Detection.** Not implemented unless the pinned processor exposes language identification
  without a second model; if it does, add "Detect" to the menu, otherwise leave it out and say
  so here.
- **Search.** Unchanged; `unicode61 remove_diacritics 2` already handles other Latin-script
  languages.
