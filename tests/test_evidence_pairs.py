"""Evidence bundles must describe the relation they are asked about.

pattern_evidence was keyed by (pattern_type, pattern_id), which cannot express a
pair. Leverage, decision impact and tension are all pairwise — they run once per
(source, target) and stored the bundle under the source alone — so a source with
two targets had two bundles competing for one key, and the "latest bundle" for
that source and engine was whichever pair happened to run last.

The practical effect: asking why IRIS says A tends to precede B could be
answered with the numbers for A and C.
"""

from datetime import datetime

from agent.database import db
from agent.evidence import EvidenceEngine


def _theme(user_id: int, name: str) -> int:
    """A real theme to hang evidence on.

    These ids used to be bare literals (404, 505, 808). Evidence is purged per
    user by matching the ids of themes that user owned, so evidence written
    against a number with no theme behind it was never cleaned and survived the
    whole session — and when the themes sequence later reached that number, an
    unrelated test counting rows for its own theme picked up the orphans too.
    """
    now = datetime.now().isoformat()
    return db.create_theme(user_id, [0.1] * 1536, name, now, now)


def _bundle_values(bundle):
    return {r["evidence_key"]: r["evidence_value"] for r in bundle}


def test_two_relations_of_one_source_keep_separate_bundles(test_user):
    ev = EvidenceEngine()
    source = _theme(test_user["id"], "source")
    target_b = _theme(test_user["id"], "target b")
    target_c = _theme(test_user["id"], "target c")

    ev.record_evidence(
        "leverage", "theme", source,
        [{"type": "rate", "key": "p_target_given_source", "value": 0.8}],
        related_pattern_id=target_b,
    )
    ev.record_evidence(
        "leverage", "theme", source,
        [{"type": "rate", "key": "p_target_given_source", "value": 0.1}],
        related_pattern_id=target_c,
    )

    b = _bundle_values(ev.get_latest_bundle("theme", source, "leverage", target_b))
    c = _bundle_values(ev.get_latest_bundle("theme", source, "leverage", target_c))

    assert b["p_target_given_source"] == 0.8, (
        "the bundle for A→B must describe A→B, not whichever pair ran last"
    )
    assert c["p_target_given_source"] == 0.1


def test_a_single_pattern_engine_is_still_addressable_without_a_pair(test_user):
    """related_pattern_id is NULL for persistence, trajectory and resolution.
    Matching is IS NOT DISTINCT FROM, so passing None finds them — `= NULL`
    would have matched nothing and silently emptied every explanation."""
    ev = EvidenceEngine()
    theme_id = _theme(test_user["id"], "single pattern")
    ev.record_evidence(
        "resolution", "theme", theme_id,
        [{"type": "count", "key": "recent_count", "value": 3}],
    )

    bundle = ev.get_latest_bundle("theme", theme_id, "resolution")
    assert _bundle_values(bundle) == {"recent_count": 3}


def test_a_pairwise_bundle_is_not_returned_for_the_wrong_pair(test_user):
    ev = EvidenceEngine()
    anchor = _theme(test_user["id"], "anchor")
    measured = _theme(test_user["id"], "the pair that ran")
    other = _theme(test_user["id"], "a pair with no evidence")
    ev.record_evidence(
        "impact", "theme", anchor,
        [{"type": "delta", "key": "delta_score", "value": -0.4}],
        related_pattern_id=measured,
    )

    assert ev.get_latest_bundle("theme", anchor, "impact", other) == [], (
        "a relation with no evidence must return nothing, not another pair's"
    )


def test_the_whole_pattern_view_shows_every_relation(test_user):
    """Asked for a theme with no engine named, the view is all of its
    relations — one bundle per (engine, other end) — rather than one relation
    standing in for all of them."""
    ev = EvidenceEngine()
    source = _theme(test_user["id"], "source with two relations")
    first = _theme(test_user["id"], "first target")
    second = _theme(test_user["id"], "second target")
    ev.record_evidence("leverage", "theme", source,
                       [{"type": "count", "key": "target_id", "value": first}],
                       related_pattern_id=first)
    ev.record_evidence("leverage", "theme", source,
                       [{"type": "count", "key": "target_id", "value": second}],
                       related_pattern_id=second)
    ev.record_evidence("resolution", "theme", source,
                       [{"type": "count", "key": "recent_count", "value": 5}])

    bundle = ev.get_latest_bundle("theme", source)
    targets = {r["evidence_value"] for r in bundle if r["evidence_key"] == "target_id"}
    engines = {r["engine_name"] for r in bundle}

    assert targets == {first, second}, f"both relations must appear, got {targets}"
    assert engines == {"leverage", "resolution"}
