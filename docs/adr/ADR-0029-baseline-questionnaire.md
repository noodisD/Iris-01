# ADR-0029: The owner answers a questionnaire inside IRIS, in their own words

## Status
Accepted — 2026-10-06

## Context
The owner's practice gave them a long intake questionnaire (123 open questions
in eight sections, in Polish) whose purpose is to map the context of a life
rather than to diagnose. The owner wants to answer it inside IRIS so that IRIS
knows them better, by form or in conversation, with answers used in chat and
as evidence and their revisions kept. The questionnaire is someone else's
copyrighted text; the IRIS repository is public.

## Decision
- **The text stays local.** The questions and their translation live in
  `data/questionnaires/<name>.json`, which is gitignored. The code knows only
  the shape (sections, intros, questions with `pl` and `en`). Without the file
  the screen says the questionnaire is not installed.
- **Drafts go nowhere.** Answers are drafted in `questionnaire_answers`
  (migration 0048) and sent nowhere until the owner adds a section, at a click
  that shows the cost first. One click per section means one pattern update,
  not one per answer.
- **An added answer is an owner-only source.** It becomes a reflection
  (`source='questionnaire'`) in the session format of ADR-0028 with kind
  `questionnaire`: the question, or IRIS in an interview, is the `asker`, whose
  turns are context; only the owner's turns can be cited. The reader, idea
  checks and chat recall need nothing new.
- **The interview never writes the answer.** IRIS asks the question, asks at
  most two follow-ups about what the question asks for, accepts "skip" and
  stops after three replies. The draft is the owner's replies word for word,
  editable before saving. Only the question and that exchange are sent.
- **Revisions keep history.** Revising an added answer makes a new version;
  the old one is marked superseded and kept, and its reflection is removed so
  only the current answer is evidence.
- **Answers are not recent writing.** They are left out of chat's recent
  entries, the Journal list and the weekly letter, and recalled in chat by
  passage as "questionnaire answer".

## Consequences
- What the owner says about reasons and feelings in answers can anchor
  insights, which writing alone rarely did (25 of 165 events stated a reason).
- A revised answer replaces the old one as evidence; how an answer changed is
  visible in its history, not in patterns.
- Another questionnaire needs only another local file with the same shape.

## Suggested answers (2026-10-06)
At the owner's click, IRIS suggests drafts for a section's empty questions
from the owner's own writing (migration 0049). For each question the journal,
sessions and chat are searched by meaning; a model picks up to four sentences
that answer it, and each is found again word for word in its source (a session
quote only in the owner's own turns). The suggestion is those quotes with where
and when they were written; nothing is paraphrased, and a question nothing
answers stays empty. A suggestion never replaces what the owner wrote. Kept
unchanged, or edited around its quotes, it is added as memory but not evidence,
since its sentences already count in their own entries; rewritten in the
owner's words, it counts like any answer.
