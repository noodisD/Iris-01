# ADR-0020: Opening chat starts an empty session

## Status
Accepted — 2026-09-24

## Context
Chat was one rolling transcript. Opening it on the phone or web showed the stored history from the top. The owner wants each open to start empty, on both clients, without discarding what was said or skipping analysis.

## Decision
`POST /api/conversations` creates an empty `chat_sessions` row. The web and Android chat screens call it each time chat is opened. `GET /api/conversations/{id}/messages` returns only that session. Messages remain in `conversation_messages`, queued for embedding, and are available to a later reply as stored earlier conversation rather than as the visible transcript. `GET /api/conversations/current` returns the latest session; it does not start a new one unless the user has none.

## Consequences
A chat open no longer continues the previous transcript on screen. Recall of earlier chat depends on the stored messages and their embeddings, not on rendering them. A session id that was not opened cannot be streamed to. Revisit this only if the owner wants the rolling transcript back on either client.
