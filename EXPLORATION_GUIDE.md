# Reading the IRIS code

A route through the code, following what happens to what the owner writes. Read
[ARCHITECTURE.md](ARCHITECTURE.md) sections 1 and 2 first for the map, and
[CONTEXT.md](CONTEXT.md) when a word means something specific here. Each stop names
the function to open and the question it answers. The questions at the end are the
ones worth being able to answer without looking.

---

## Route 1: an entry, from Save to chat

1. **The write.** `iris_api.py` journal routes → `agent/trackers/reflections.py`
   `ReflectionService.create_reflection` → `agent/database.py` `create_reflection`.
   *Why is the queue row inserted inside the same transaction as the entry?*
   (`Database._queue`, ADR-0011.)
2. **The queue.** `agent/work_queue.py` `process_due` claims due jobs under a lease and
   `_run` dispatches by kind. *What happens when a job fails six times? What does
   `generation` protect against?*
3. **Processing.** `agent/pipeline.py` `run_processing_pipeline`: read the row back by
   id, embed it, `_index_entry_passages` (long entries), `readable.ensure_copy`
   (dictated ones), then theme matching. *Why is the row read back by id rather than
   taken from the job?*
4. **Reading.** `agent/discovery_worker.py` `process_reflection` →
   `agent/episodes.py` `EpisodeReader.read` (accounts with verbatim quotes) →
   `verify_reading` (each field checked by `connections.check_account_fields`) →
   `agent/discovery.py` `_store_reading`. *Why must every quote be found word for word
   in the source, and what happens to a field whose quote does not support it?*
5. **Synthesis.** `agent/discovery.py` `process_user` → `agent/connections.py`
   `discover_dynamics`: propose, merge, membership, identity, refine;
   `agent/discovery_memo.py` remembers verdicts already paid for. *Why does one edit
   make the whole run start again, and what stops it adding forty new patterns at
   once?*
6. **Showing it.** `agent/personal_patterns.py` and `agent/personal_insights.py`
   project the stored draft for a range; `iris_api.py` `/api/patterns` and
   `/api/personal-insights`; `frontend/src/screens/PatternsScreen.tsx`.
7. **Chat.** `agent/core.py` `PersonalAICompanion.begin_turn` →
   `_get_aggregated_context` (each section: `_get_relevant_context`,
   `_questionnaire_context`, `approved_context.py`) → `stream_reply` →
   `agent/intelligence.py` `Intelligence.stream`, with the rules in
   `prompts/system_prompt.py`. *Which memories can chat see, how are they found
   (`database.search_similar_embeddings`, exact since migration 0052), and how does it
   know which words in a session were the owner's?*

## Route 2: a therapy session, from recording to evidence

1. `agent/session_imports.py` `SessionImports.stage_recording` keeps the file; nothing is
   sent. `start_voices` is the owner's click.
2. `agent/session_voices.py` `run` → `_transcribe`: `_diarize` (who spoke when, with the
   stored voice samples) and `agent/local_whisper.py` `words` (what was said, locally),
   joined by `assign`; then `agent/session_cleanup.py` `tidy` fixes mis-hearings against
   the second hearing and logs every change.
3. `apply_transcript`, then `commit` writes the reflection in the session format
   (`agent/sessions.py` `compose`, `read`).
4. Processing cuts it into passages of whole turns and adds English vectors
   (`pipeline._index_session`, `gloss_session_passages`); reading takes 25 turns at a
   time (`sessions.parts`). *Where is the rule that only the owner's turns are evidence
   enforced?* (`sessions.owner_turn` and its callers.)

## Route 3: the older analytical engines

1. **Themes.** `agent/persistence.py` `PersistenceEngine` matches an entry to themes by
   cosine similarity, or clusters to find a new one, in the space built by
   `agent/comparison.py` (the owner's shared voice removed, ADR-0014).
2. **Measures.** `agent/trajectory.py` (frequency over time), `agent/tension.py`,
   `agent/resolution.py`, `agent/leverage.py`, `agent/decision_impact.py`,
   `agent/lifelong.py`.
   - Direction labels: "emerging", "increasing", "stable", "fading", "insufficient data"
3. **Admission.** `agent/pipeline_orchestrator.py` `canonical_pipeline` then `admit`:
   coverage, enablement, confidence (`confidence.py`), conflict suppression
   (`conflict.py`, `conflicts.py`), ranking (`prioritization.py`). *Why do chat and the
   screen share one admission function?* (ADR-0007.)
4. **Language.** `agent/narrative.py` `NarrativeFormatter` with
   `narrative_templates.py`, checked by `narrative_policy.py`. *Why is a finding that
   cannot be phrased neutrally dropped rather than reworded?*

## Around the routes

- **Ideas:** `agent/ideas/service.py` `discover` (reading), `store.py` (no model calls),
  `reader.py` (prompts and parsing).
- **Questionnaire:** `agent/questionnaire.py` (drafts, sections, revisions),
  `questionnaire_interview.py` (the draft is the owner's own replies),
  `questionnaire_suggest.py`, `questionnaire_context.py` (what chat sees).
- **Access:** `scripts/serve_iris.py` opens the doors; `agent/mobile_auth.py` decides who
  may use which.
- **Observability:** `agent/observability/tracing.py` (the API every call site uses),
  `processors.py` (what is stored), `health.py` (the Observatory's verdicts).
- **The doctor:** `agent/doctor/__init__.py` (the framework), then the three
  `checks_*.py` files; `docs/runbooks/`.
- **Schema:** `agent/migrations.py` and `migrations/`; `tests/schema_snapshot.json`.
- **Tests:** `tests/conftest.py` keeps the suite offline (the model, embeddings and
  transcription are stubbed) and on a separate test database.

## Questions worth answering without looking

1. What is the path of one journal entry from Save to appearing in a pattern?
2. Why is a quote that is not found word for word in its source treated as a bug, not
   a paraphrase?
3. What makes a session's therapist turns impossible to quote as the owner's?
4. Why was memory search returning the wrong memories until migration 0052, and how
   would you notice if it happened again? (`retrieval.complete` in the doctor.)
5. Why does a restart during a pattern update cost an hour, and what tells you whether
   one is safe? (`python -m agent.doctor --can-restart`.)
6. What reaches a model, when, and who decided it should?
7. Where do the older engines still matter, and why are they kept?
