# ADR-0028: A therapy session is the owner's evidence only where the owner speaks

## Status
Accepted — 2026-10-03

## Context
The owner records their therapy sessions, most weeks, and has them transcribed
with speaker labels. A session may be the richest source IRIS has: the owner
describing, out loud and at length, what happened and how they meet it. But two
people speak in it. Everything IRIS concludes stands on quotes that are the
owner's own words, and a therapist's question, summary or interpretation read
as the owner's would come back out of the engines as "what you said". A journal
entry has no such problem, so nothing in the reader, the idea checks or chat
told one speaker from another. The transcripts also mark some turns as
uncertain, and an hour of talk is too long to embed or to paste into chat.

## Decision
- **One entry, speakers kept.** A session is one dated reflection with
  `content_format` and `source` `session` (migration 0047). Its text begins
  with the speakers named (`owner:`, `therapist:`, plus kind, start time and
  language), then one paragraph per **turn**: one speaker's uninterrupted
  stretch, with its start time. Consecutive transcript segments by one speaker
  become one turn; no word is changed, translated or dropped. The text carries
  the roles itself, so every reader holding an entry's content can tell whose
  words a span is (`agent/sessions.py`).
- **Roles come from the exact label.** Exactly the owner's label is the owner;
  exactly the therapist's is the therapist; any other label, including one the
  transcriber marked uncertain, is **unclear**. Guesses on the import screen are
  only defaults.
- **Only the owner's turns are evidence, mechanically.** The patterns reader
  accepts a quote only inside one owner turn, and its citation is that whole
  turn; an account whose quotes fall in the therapist's or an unclear turn is
  dropped, as is one that would join two owner turns, since the words between
  them are someone else's. The shared quote check used by ideas does the same,
  and an idea's stance check sees the quote's turn with the turns either side,
  not the whole hour. The weekly letter checks quotes against the owner's words
  only, and a session is not counted as writing.
- **The rest is context, labelled.** A model reading a session is told who is
  who and sees every turn with its speaker and role. Chat recalls a session by
  **passage** — whole turns, each naming its speaker, embedded one passage at a
  time (`session_passages`) — and is told the therapist's turns and unclear ones
  are never the owner's. Recent entries name a session in one line instead of
  pasting it. A session is not a theme occurrence.
- **Staged, then the owner's click.** An uploaded transcript waits in
  `session_imports`, sent nowhere. It can be imported only when the owner has
  given the day and local time and said which speaker they are. The screen
  shows what importing sends to OpenAI and what it costs before the click.
  Importing indexes it for chat and queues the ordinary reading; undo takes it
  back out of the journal to fix and import again. The same transcript cannot
  be imported twice.

## Consequences
- Sessions can feed patterns, ideas and chat without the therapist's words
  ever being quoted as the owner's. What the owner only agreed to ("yes,
  exactly") cannot become evidence; the owner's own sentences can.
- Short owner turns carry less: an account needs its situation and response
  inside one uninterrupted stretch of the owner speaking.
- Better speaker labels mean more evidence. Turns left unclear are kept, but
  never count; fixing a label means undoing the import, correcting the
  transcript and importing again.
- Changing how a session is shown to the reader does not re-read sessions
  already read; the reader version still covers the general prompt only.
- Revisit if sessions with more than two people, or other recorded
  conversations, are wanted: the roles would need more than owner, therapist
  and unclear.

## A recording with no transcript (2026-10-07)
A session can be staged from its recording alone. It is kept on this machine
and sent nowhere until the owner clicks "Transcribe the recording", with the
cost shown first. The recording is then written down speaker by speaker
(gpt-4o-transcribe-diarize). Voices kept locally in `data/sessions/voices/`
(`owner--<label>.wav`, `therapist--<label>.wav`) let it name the speakers; a
voice it cannot match is unclear. Without kept voices each voice keeps a
letter for the owner to name. The owner then checks who is who, gives the day
and time, and imports, as with a transcript.
