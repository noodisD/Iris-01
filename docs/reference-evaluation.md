# Personal dynamics: reference and release checks

The v4 diagnostic cache is **not** a discovery-table import. It reads only
eligible, accepted original reflections for one owner, using the same per-entry
extractor and contextual field checker as the worker. Provider failures are
unavailable, not empty evidence. The old `data/episodes.json` and old reference
judgments remain historical; never transfer verdicts by array index.

## Owner review of actual writing

Run from the development checkout, with a configured local PostgreSQL instance.
Each file is owner-only (mode 0600), has a new v4 name, and refuses overwrite.
Never commit these source passages, judgments or checker responses.

```bash
uv run python scripts/read_episodes.py --dry-run
uv run python scripts/read_episodes.py --cache data/episodes-v4.json
uv run python scripts/read_episodes.py --reuse --cache data/episodes-v4.json
uv run python scripts/spot_check.py --cache data/episodes-v4.json --count 10
uv run python scripts/reference_labels.py build --cache data/episodes-v4.json --count 10
```

Review the original enclosing paragraph, actor, record kind (event,
self-report, intention or hypothetical), source date versus event time, each
extracted field, missing outcomes, possible retellings and any negation. The
spot-check sheet is a manual extraction audit, **not** semantic validation of
the whole archive. Enter one judgment per populated grounded field in the new
`data/reference-labels-v4.md`: `supported`, `not_stated`, `contradicted`,
`wrong_modality`, `wrong_actor` or `unsure`. A located quote alone is not
contextual support; do not reuse earlier sheet judgments.

```bash
uv run python scripts/reference_labels.py read --cache data/episodes-v4.json
uv run python scripts/verify_fields.py --reviewed --dry-run \
  --cache data/episodes-v4.json --reference data/reference-labels-v4.json
uv run python scripts/verify_fields.py --reviewed \
  --cache data/episodes-v4.json --reference data/reference-labels-v4.json
```

`read` refuses blank/partial/all-unsure or changed-content references. `--dry-run`
validates cache and reference without calling a provider or writing results.
The live checker uses the **production source-selecting field checker**, not a
second agreement prompt. It records complete denominators for known errors,
supported fields and human `unsure`, with `unclear`/`unavailable` separate from
semantic rejection, and constant-support/reject baselines. A `--limit` selects
a fixed subset of validated fingerprints before model calls. Outputs remain
local at `data/field-support-v4-reviewed.json`; an unreviewed diagnostic
result cannot count as accuracy evidence.

## Independent predeclared synthetic holdout

`tests/fixtures/personal_dynamics_reference.json` has a fixed SHA-256 and
development/holdout splits: ambiguous actors and negation, plans versus
actions, missing results, retellings, motive corrections, ranges, own-purpose
counterexamples, and 24 lens positive/near-miss/excluded boundaries. The
runner refuses modified fixtures; it must not learn targets from generated
output. Run a provider-free estimate first:

```bash
uv run python scripts/evaluate_dynamics.py --dry-run --split holdout
uv run python scripts/evaluate_dynamics.py --live --split holdout \
  --out data/dynamics-holdout-<unique-run>.json
```

The live report stores exact generated sources, stage failures and a blank
independent-adjudication ledger. A human must align **every** generated
definition to reference definitions and audit every factual clause,
contradiction, owner meaning and tentative hypothesis. Count failures and
unmatched positives against fixed denominators, not just model-completed
rows. Release thresholds are ≥90% membership precision, ≥80% recall and
dynamic recovery, ≥95% factual-clause precision, zero safety errors; models
cannot grade themselves. If the provider or independent reviewer is
unavailable, the release gate remains unverified and live archive ingestion
must not be represented as complete.

The 2026-10-01 development run completed all 17 synthetic cases at the
provider stage. A separate run against the locked holdout completed 16/18:
one discovery matrix was incomplete, and one interpretation failed the
grounded-narrative check. Reports remain owner-only under
`data/personal-dynamics-development-20261001T185605Z.json` and
`data/personal-dynamics-holdout-20261001T193807Z.json`; neither completion
counts nor a model's own verdict establish semantic accuracy. Do not retry
failed holdout rows and count a successful retry as a pass. If a failed holdout
case informs prompt changes, move it into development and commission a new,
independently written holdout case before rescoring. The current gate is
**not passed**; an independent human still must adjudicate the fixed ledger.

Status and dry-run cost estimates account for complete account/definition and
event-identity matrices (up to six decisions per request) and process-lens
checks (up to four rows per request). These are planning approximations, not
spending limits: extraction can yield more than one account per reflection,
definitions and publishable groups are unknown before the read, and retry
or invalidation work is not priced in. In particular, checking every event
pair grows quadratically with the count of included events.

## Deployment boundary

First back up PostgreSQL and the original journal; retain prior archives and
pre-v4 diagnostics. Apply migration 0045 on an isolated marked test database
and run its invariants. Only after independently reviewing the holdout,
verify owner consent, provider connectivity and a live backup before running
the archive worker against the owner datastore. Monitor `GET /api/discovery/status`
for eligible/current/unread/pending/failed/excluded counts, omissions, synthesis
stage and cost estimates. A status of `failed`, `reading` or `interpreting` is
not “no patterns”; inspect original-source coverage and source revisions.
Unknown event dates and unaccepted staged material must not be silently
counted as observed events.
