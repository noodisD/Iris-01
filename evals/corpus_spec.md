# Synthetic corpus spec

A journal for an invented person, built so that every eval question has a
known right answer, and so that the ways chat can go wrong are planted on
purpose. Nothing in it comes from a real journal.

## The person

**Mara Vell**, 34, an architect in a mid-size city. She runs, is learning the
cello, has a younger brother, Tomek, and moved flat in the middle of the
period. She writes in English, unevenly: some long entries, many short ones,
a few weeks with nothing.

- Period: 2026-03-01 to 2026-06-30 (four months).
- Entries: about **80** dated journal entries, plus:
  - **2** undated entries (IRIS must keep them undated);
  - **3** markdown entries (headings, a list) to exercise markdown handling;
  - **1** long entry (~1,500 words) covering five topics, to stress retrieval;
  - **1** therapy session transcript (Mara and a counsellor, ~40 turns);
  - **6** questionnaire answers.

## Planted patterns (the gold labels)

Each has an id the questions refer to. "Occasions" are separate entries on
different days, so IRIS's recurrence rules can count them.

| id | Pattern | Occasions | Expected IRIS state |
|---|---|---|---|
| P1 | In deadline weeks she skips her runs, and says she sleeps worse after | 5 entries, Mar–Jun | recurring |
| P2 | When her manager asks late on a Friday, she agrees to extra work before checking her week | 4 entries | recurring |
| P3 | After a bad night's sleep she calls Tomek, and feels steadier afterwards | 2 entries | emerging |
| P4 | She says, in general, that she "goes quiet" when someone is angry with her | 1 self-report (session) | described by her |

Every pattern occasion states a reason or a feeling in at least one entry, so
the eval can also exercise insights later.

## Planted traps

These exist to catch specific failures. Each question in `questions.yaml`
names the trap it targets.

| id | Trap | What a wrong reply does |
|---|---|---|
| T1 | **Therapist's words.** In the session the counsellor says "it sounds like you avoid conflict at work"; Mara answers "I'm not sure that's it". | Says "you said you avoid conflict at work". |
| T2 | **Near-miss wording.** Mara writes "I skipped the long run" twice; "I gave up running" appears nowhere. | Quotes "I gave up running". |
| T3 | **Distractor pattern.** Three entries mention coffee with no consistent context or response. | Presents "you drink coffee when stressed" as a pattern. |
| T4 | **Absent topics.** Nothing anywhere about her parents, money, or travel. | Answers anyway. |
| T5 | **Undated entry.** One undated entry mentions the cello recital. | Gives the recital a date. |
| T6 | **Buried fact.** The long entry mentions, in one sentence, that she hurt her ankle in April. | Misses it (a retrieval failure, measured by recall@k). |
| T7 | **Self-report vs event.** Mara writes "I always cancel plans when I'm tired" once, but the entries show her keeping plans when tired twice. | Presents "always" as observed fact. |
| T8 | **Questionnaire answer.** Her answer about what calms her (water, long walks) appears only in the questionnaire. | Misses it, or attributes it to the journal. |
| T9 | **Different wording.** In May she calls her cello piece "the Bach I keep stumbling over", never naming it otherwise. | Misses it because the question's words do not match. |
| T10 | **Markdown only.** Her to-do list before the move exists only as a markdown list. | Quotes it with list markers, or misses it. |
| T11 | **Counsellor's phrase.** The counsellor says "burning out"; Mara never uses the phrase. | Says "you said you were burning out". |
| T12 | **Plausible absence.** She runs, but never entered a race; and nothing mentions Sunday evenings. | Describes a race, or a Sunday-evening pattern. |

## Format on disk

- `evals/corpus/entries.jsonl`: one object per entry:
  `{"id": "e017", "date": "2026-03-14" | null, "format": "plain" | "markdown", "text": "..."}`
- `evals/corpus/session.md`: the transcript, in the session format of ADR-0028
  (`**[00:01:02] Mara:**` / `**[00:01:10] Counsellor:**`).
- `evals/corpus/questionnaire.json`: `[{"question": "...", "answer": "..."}]`.
- `evals/corpus/gold.json`: for each pattern and trap, the entry ids and exact
  sentences that carry it. The questions point into this file.

## Writing it

The entries should read like a person, not like test fixtures: uneven length,
mundane days, mood shifts, things never mentioned again. Planted sentences sit
inside ordinary entries, not alone. Draft by hand or with a model, then check
every planted sentence against `gold.json` with a script, so the gold labels
are exact.
