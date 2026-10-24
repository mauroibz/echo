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

## Decisions made while implementing

- **The list is 14 languages**: the tokenizer has 183 `<|xx|>` tokens, but the pinned
  processor's `get_decoder_prompt_ids` accepts only ar, de, el, en, es, fr, it, ja, ko, nl, pl,
  pt, vi and zh. Catalan, named in this design, is not accepted and is not offered. The list is
  `models.PROCESSOR_LANGUAGES` (the window cannot import transformers, which loads torch),
  intersected with the tokenizer's tokens; a test checks it against the installed processor.
- **No "Detect"**: the processor has no language identification (only an `<|unklang|>` token
  with no API around it).
- **Choosing a language** in the transcript menu transcribes the recording again when it already
  has a transcript in another language; otherwise it only sets it. "Default (X)" clears the
  recording's own choice. `--language` on the CLI is also remembered for the recording.
- **Chinese and Japanese** passages are joined without spaces (`join_text(segments, language)`)
  and their length check counts two characters as a word; without that every passage looked
  implausibly short and was retried twice.
- **Verification (1.1)**: one synthesized sentence per language (espeak-ng) through the real
  model on the GPU. Word-perfect: es, en, fr, de, it, pl, zh. Recognizable with errors from the
  robotic voice: pt, nl, el, ko, vi, ar. Japanese failed because espeak-ng reads kanji aloud as
  "Chinese letter"; the clip, not the model, was at fault. The style sentence left the word
  count unchanged for es (17 and 17) and en (17 and 17).
