# ADR-0026: An idea has a page the owner writes, and wording the owner can change

## Status
Accepted — 2026-09-28

## Context
Ideas were read-only apart from position and area. The glossary said a
statement never changes once proposed. In practice the owner wants to fix
the wording Iris proposed, and to think about an idea in their own words, with
links between ideas, as they do in Obsidian.

## Decision
- **Wording.** The owner may reword an active or proposed idea
  (`PATCH /api/ideas/{id}` with `statement`). Rewording states the same
  proposition better. A different proposition is still a new idea. A wording
  that another idea already has is refused (409) rather than merged. The
  quotations stay attached; a critique made before the change is marked out of
  date, because its basis changed.
- **Notes.** Each idea has `notes`, Markdown of up to 20,000 characters
  (migration 0041). Writing saves itself. `[[wording]]` or
  `[[wording|shown text]]` links to the idea with that wording. Links are
  matched as statements are, ignoring case and spacing. The page lists the
  ideas whose notes link to it.
- **Renaming keeps links.** When an idea is reworded, every `[[link]]` to it in
  the owner's notes is rewritten to the new wording in the same transaction.
  Shown text after `|` is kept.
- **Notes are not evidence.** They are never quotations and never count
  towards an idea. They are not sent to any model: not to discovery, links,
  meanings, critique or chat.

## Consequences
- Link and meaning proposals use the current wording, so a reworded idea is
  judged as it now reads.
- Notes are web-only. The phone app has no Ideas screen.
