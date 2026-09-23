# Field-checker evaluation: trustworthy bookkeeping first

This change repairs the evaluation harness, **not the checker’s judgment**.
It does not admit or exclude accounts, restore downstream analysis, or validate
the archive. No extraction, discovery, or provider run is part of this change.

## What changed

- A reference must contain every account listed in its recorded cohort, and a
  verdict for each populated response/outcome field. Blank, partial, invalid,
  missing, ambiguous, and stale references stop before importing the model client.
- Explicit `unsure` remains a human judgment, separate from an unanswered field.
  It gets its own output distribution and is not scored as correct or erroneous.
  An all-unsure reference cannot support a scored run and is refused.
- The old short account key remains a locator. A separate SHA-256 fingerprint
  covers the entire cached account, including actor, modality, outcome, full
  citations, and dates. Citation order is immaterial; changes to content are not.
- Missing results, missing verdict fields, and `unavailable` stay in the complete
  reference denominators. Reports show errors caught, correct fields rejected,
  and unavailability separately, alongside always-support and always-reject
  baselines. An unavailable result is not a semantic abstention.
- Malformed JSON shapes and duplicate verdict fields are unavailable rather than
  crashes or last-value-wins decisions. This parser change bumps checker version
  to 2; the prompt is unchanged. Provider exceptions log their type, not payloads.
- Reviewed runs save their results, exact selected reference, scores, model name,
  and prompt hash to `field-support-reviewed.json`. Ordinary unreviewed runs
  retain the separate `field-support.json` destination. Neither may overwrite
  the input cache or reference through `--out`.
- `--limit` is an explicit subset of the fully validated reference, chosen
  before asking the model. Failed answers never determine that subset.
- Pure helpers and dry runs no longer load application/database modules through
  `agent` package imports. Public application exports resolve lazily on request.

## Preserve the old sheet; build a versioned replacement

Run these commands from the development checkout, using an existing environment.
Replace the cache path if necessary. They do not ask a model anything:

```bash
/home/noodis/Iris-01/.venv/bin/python -B scripts/reference_labels.py build \
  --cache /home/noodis/Iris-01/data/episodes.json \
  --sheet /home/noodis/Iris-01/data/reference-labels-v2.md
```

The builder refuses to overwrite an existing sheet. It retains the original
ten positional selections `(0, 1, 2, 3, 4, 9, 10, 48, 61, 72)`: before building
against a replaced or reordered archive, confirm that this is still the intended
spot-check cohort. Once built, matching is by key and content, not position.

The owner fills in the judgments. Do not infer them from the old scoring script
or automatically transfer them from an unfingerprinted sheet. Then:

```bash
/home/noodis/Iris-01/.venv/bin/python -B scripts/reference_labels.py read \
  --cache /home/noodis/Iris-01/data/episodes.json \
  --sheet /home/noodis/Iris-01/data/reference-labels-v2.md \
  --out /home/noodis/Iris-01/data/reference-labels-v2.json

/home/noodis/Iris-01/.venv/bin/python -B scripts/verify_fields.py --reviewed --dry-run \
  --cache /home/noodis/Iris-01/data/episodes.json \
  --reference /home/noodis/Iris-01/data/reference-labels-v2.json
```

Removing `--dry-run` sends passages to the application's configured provider;
that is a separate evaluation step, not part of this implementation. The
unreviewed mode still exists and must not be confused with an evaluation.

## Verification and boundaries

The synthetic regression suite runs without the repository's database fixtures:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/noodis/Iris-01/.venv/bin/python -B -m pytest \
  --noconftest -p no:cacheprovider tests/test_reference_evaluation.py
```

It covers stale fingerprints, changed evidence, complete cohort enforcement,
duplicate/invalid labels, dry-run and preflight call boundaries, unavailable
denominators, constant baselines, malformed provider replies, and synthetic
artifact persistence. Verification on 23 September 2026: **72 tests passed**;
Ruff passed on all six changed Python files; mypy passed on the four pure
helper/package/script files; `git diff --check` passed. The checker parser was
tested with an isolated import and fabricated provider replies, not a live API.

Development is based on `7ddc454`, branch `feat/iris-development`, in the isolated
worktree `/tmp/iris-reference-dev.faZ9qE`. The shared checkout switched to an
unrelated architecture branch during work; these changes were kept separate and
have not been merged into it. They are kept on the dedicated development branch
for review and integration.

This is not a full application or live-provider integration test. The normal
suite provisions and truncates a dedicated database, so it was not run here.
No human reference judgments were filled in. Ten reviewed accounts remain a
development sample, not a calibration or archive-wide validation set. The
next experiment still needs separate held-out accounts and owner judgments.

The TypeSafe skill informed the separation of operational failures from semantic
judgments. No TypeSafe SDK or Jev integration was added. TypeSafe itself advises
testing confidence thresholds on the target use case; interface guarantees are
not evidence that this checker works. [Official confidence guidance](https://docs.typesafe.ai/confidence),
consulted 23 September 2026.
