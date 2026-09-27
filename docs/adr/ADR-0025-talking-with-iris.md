# ADR-0025: Talking with IRIS is chat with speech around it

## Status
Accepted — 2026-09-27

## Context
The owner wants to talk with IRIS aloud, hands-free, on the laptop and the
phone, in English. They chose to keep only the words: what they say should be
saved like typed chat, and the audio should not be kept.

There are two ways to build this. A realtime speech-to-speech model answers in
under a second, but it is a different and weaker reasoning model than the one
chat uses, costs roughly five to ten times more per minute, and would need
IRIS's whole context squeezed into its instructions. The alternative wraps
the existing chat turn in two conversions.

## Decision
A spoken turn is an ordinary chat turn with speech around it.

- **In:** the client detects the end of an utterance and sends it to
  `POST /api/voice/transcribe` (`agent/voice.py`). It is written to a
  temporary file under `data/tmp/` for one transcription request with
  `TRANSCRIPTION_MODEL` and an English hint, then deleted in `finally`,
  whether the request succeeds or not. At most 5 MB is accepted per turn.
- **The turn:** the text goes to the same
  `POST /api/conversations/{id}/messages/stream` as typing, with
  `"voice": true`. Storage, context, the approved block and error events are
  unchanged. The only difference is one extra system-prompt block: the reply
  will be heard, so it uses plain spoken English, two to four sentences, and
  at most one question.
- **Out:** the client splits the streamed reply into sentences and asks
  `POST /api/voice/speech` for each, at most 600 characters. That route
  streams MP3 from `TTS_MODEL` with a calm tone instruction. The client plays
  the sentences in order and stops at once when the owner talks over IRIS.
- **Cost first:** `GET /api/voice/estimate` gives the price of one turn
  without calling any model. Talk mode shows it, and nothing is sent until
  the owner presses Start talking.
- **What reaches OpenAI:** the owner's speech (for transcription); their
  words and IRIS's context (for the reply, as with typed chat); IRIS's reply
  (for speech). Logs record sizes and costs, never words.

## Consequences
Each turn pauses for about two to four seconds while IRIS transcribes,
thinks and starts speaking. That is slower than a realtime model, but IRIS
answers with its full context and its usual model, and a spoken turn is
indistinguishable in the record from a typed one. An interrupted reply is
still saved in full, because the reply is written before it is spoken; only
its playback stops. Switching to a realtime model later would replace the
client's loop, not the record.
