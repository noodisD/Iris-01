# ADR-0030: A session recording's words are written down locally by Whisper, then checked

## Status
Accepted — 2026-10-12

## Context
A session imported from its recording alone (ADR-0028) was written down by the
hosted diarizing transcriber, which is good at telling voices apart but whose
words drift on a long Polish recording. One session came back at a speaking
rate a fifth above the owner's other session, with dozens of phrases repeated
word for word, a loop, and sentences that made no sense. Re-transcribing each
turn on its own with the hosted plain transcriber lost speech instead: a fifth
of the long turns kept under half their words, and three turns returned the
prompt. Whisper large-v3, run locally on the owner's GPU, wrote the same
recording at the owner's normal rate with almost no repeats, in about seven
minutes for an hour of audio.

## Decision
- **Words from local Whisper, speakers from the diarizer.** With
  `WHISPER_PYTHON` set to the Python of an environment that has faster-whisper,
  `local_whisper.words` writes the recording down word by word with times, in a
  separate process (`scripts/whisper_words.py`) so the server never loads the
  model or holds GPU memory. Each word goes to the voice the diarizer heard
  when it was said (`session_voices.assign`); a word far from any voice is
  unclear. The diarizer is still asked, as before, with the stored voice
  samples.
- **Checked against the second hearing.** `session_cleanup.tidy` sends each
  stretch of twenty turns with the diarizer's words for the same time to the
  chat model, which may fix only plain mis-hearings, preferring the other
  hearing's word, and marks what neither settles as unclear rather than
  guessing. A turn whose length moves by more than a fifth keeps Whisper's
  words; every word change is logged in the import's report for the owner to
  read; a failed request leaves its turns alone.
- **Same click, same cost first.** It runs on the existing "Transcribe" click.
  The estimate now says the words are written on this computer and adds the
  check (about half a cent a minute) to the diarizer's price.
- **Without Whisper, nothing changes.** Where `WHISPER_PYTHON` is unset, or
  Whisper fails, the diarizer's own words are used and the report says why.

## Consequences
- Session words are better and the audio's words never leave the machine for
  transcription; the audio still goes to OpenAI to tell the voices apart.
- A model touches the words, which `readable.py` otherwise forbids. That rule
  is about the owner's written text, which is what they meant; here the input
  is a machine's guess at speech, the fixes are constrained to a second
  hearing, and the log makes each one visible.
- The voices pass on an existing transcript is unchanged: it only relabels.
