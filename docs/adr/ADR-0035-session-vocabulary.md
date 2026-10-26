# ADR-0035: A local list of session terms steadies the search gloss

## Status
Accepted — 2026-10-26

## Context
Sessions are in Polish and the owner asks chat in English. The English gloss
(ADR-0031) lifted English-question recall of session passages from three in
ten to ten in ten, but a practitioner's recurring terms are idiolect: a word
whose everyday sense is a meadow can mean a family's unspoken climate. The gloss
translates such terms literally, so an English question about the idea misses
the passage that names it.

## Decision
- **One local file, never in the repository.** `data/sessions/vocabulary.json`
  holds `{"terms": [{"pl": …, "en": …}]}` (`agent/session_vocabulary.py`).
  Without the file, or when it cannot be read, nothing changes.
- **The gloss renders each term the same way.** `gloss_session_passages`
  adds one line, `Render these recurring terms as given: pl → en; …`, to the
  translation prompt, so search finds the idea by its English name.
- **Search only.** The list never reaches chat, the reader or patterns. It
  carries renderings, not anyone's interpretations, and the passage chat
  shows is still the words as said.
- **Not given to Whisper.** faster-whisper's `hotwords` was tried on a
  real session of about 50 minutes, with and without the list. The list run
  found no term the plain run missed, wrote 4% fewer words, and left two
  half-minute stretches of speech almost empty (about 40 words each down to
  one). Losing speech costs more than a mis-heard term, which the second
  hearing (ADR-0030) can still fix.

## Consequences
- Existing passages keep their old English vectors until they are glossed
  again, at one worker call and one embedding per passage.
- A wrong rendering in the list skews search for that term; the owner edits
  the file.
