# ADR-0033: The web chat reopens the conversation last written in

## Status
Accepted — 2026-10-13. Supersedes [ADR-0020](ADR-0020-chat-opens-a-new-session.md) for the web app.

## Context
ADR-0020 made every chat open start empty. In use, a page reload lost the
conversation on screen, and earlier conversations could not be reached at all:
the owner asked why "it auto resets and last sessions are not available". The
same rule left an empty `chat_sessions` row on every visit (118 of 129).

## Decision
- **Reload reopens.** The web chat opens the conversation named in the address
  (`?c=<id>`), else the one last written in (`GET /api/conversations/current`
  now means "last active", not "last created").
- **Earlier conversations are listed** (`GET /api/conversations`, with how each
  began and whether it was added to IRIS) and can be reopened and continued; the
  companion reads that conversation's own history.
- **New conversation is a click**, disabled while the current one is empty.
  Opening chat from a pattern or insight still starts a fresh one.
- **An empty open is reused** (`create_chat_session`), so visits no longer leave
  empty rows behind.

## Consequences
The phone app still opens an empty conversation each time (ADR-0020 holds there);
the server reuses an empty one, so it leaves no clutter. Recall of other
conversations through stored messages is unchanged.
