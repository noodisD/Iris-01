# ADR-0032: A chat conversation is evidence only when the owner adds it

## Status
Accepted — 2026-10-12

## Context
An audit found that of 166 events the owner reported doing, 12 state a
reason, 32 a feeling, and 4 a later outcome. The reader is right to record a
reason only when the owner gives one (`episodes.py`: "what the owner says
explains it, NOT your explanation"). The owner rarely writes reasons in
entries. They do give them in chat, where IRIS asks one question at a time
about what led to something, how it felt and what happened after.

Chat messages were embedded for recall in later chats, but never read for
patterns or ideas.

## Decision
- **The owner adds a conversation with a click.** "Add to IRIS" sits under the
  chat composer and shows the cost first, under a tenth of a cent on the
  worker model. Nothing is added automatically.
- **An added conversation is a session-format reflection** (`source 'chat'`,
  `session: chat`, migration 0051), shaped like a questionnaire interview.
  IRIS's turns are the asker's, so context. The owner's turns are evidence,
  and every rule from ADR-0028 applies unchanged: a quote must lie in one
  owner turn, and an account resting on IRIS's words is not kept.
- **Adding again replaces.** A conversation that went on can be updated.
  `chat_sessions` records the reflection and how many messages it held, so the
  new copy replaces the old and IRIS never reads two overlapping copies.
- **Kept out of what chat already shows.** An added chat is not a recent
  entry, does not appear in the Journal list, and gets no session passages,
  because its messages are already recalled one by one.

## Consequences
- Reasons, feelings and outcomes the owner says in chat can now support
  patterns and ideas, under the same owner-only rule as sessions.
- A chat the owner never adds is unchanged: recalled in later chats, and
  never evidence.
