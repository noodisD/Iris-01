# ADR-0035: A local list of session terms helps Whisper and the search gloss

## Status
Accepted — 2026-10-26

## Context
Sessions are in Polish and the owner asks chat in English. The English gloss
(ADR-0031) lifted English-question recall of session passages from three in
ten to ten in ten, but a practitioner's recurring terms are idiolect: a word
whose everyday sense is a meadow can mean a family's unspoken climate. Whisper
mishears such terms, and the gloss translates them literally, so an English
question about the idea misses the passage that names it.

## Decision
- **One local file, never in the repository.** `data/sessions/vocabulary.json`
  holds `{"terms": [{"pl": …, "en": …}]}` (`agent/session_vocabulary.py`).
  Without the file, or when it cannot be read, nothing changes.
- **Whisper listens for the terms.** `local_whisper.words` passes the Polish
  terms as faster-whisper's `hotwords` when the recording may be Polish.
  `condition_on_previous_text` stays off. Hotwords can bias Whisper towards a
  term that was not said; the second hearing (`session_cleanup.tidy`,
  ADR-0030) still checks every stretch.
- **The gloss renders each term the same way.** `gloss_session_passages`
  adds one line, `Render these recurring terms as given: pl → en; …`, to the
  translation prompt, so search finds the idea by its English name.
- **Search only.** The list never reaches chat, the reader or patterns. It
  carries renderings, not anyone's interpretations, and the passage chat
  shows is still the words as said.

## Consequences
- Existing passages keep their old English vectors until they are glossed
  again, at one worker call and one embedding per passage.
- A wrong rendering in the list skews search for that term; the owner edits
  the file.
