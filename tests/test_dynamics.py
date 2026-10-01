"""Provider-free regression cases for provisional membership and event identity gates."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from agent.dynamics import (
    Definition, DiscoveryDraft, FieldCheck, FieldChecks, GroundedClause,
    Membership, PairDecision, QuoteRef, bind_dynamic_ids, claim_hash,
    count_independent, definition_key, derive_role, dynamic_id, evidence_state,
    mutually_independent, partition_events, project_range, snapshot_hash,
    validate_field_checks, validate_matrix,
)
from agent.episodes import Episode
from agent.observations import Citation
from agent.reference_evaluation import account_fingerprint


D = date(2026, 9, 30)


def account(entry: int, *, day: date | None = D, actor: str = "self",
            kind: str = "event") -> tuple[str, dict]:
    situation = "Someone was waiting for a response."
    response = "I answered before checking my capacity."
    text = situation + " " + response + " I wrote this to remember it."
    episode = Episode(actor=actor, record_kind=kind, situation=situation, response=response,
                      demand=None, information=None, feeling=None, concern=None,
                      immediate_outcome=None, later_outcome=None, explanation=None,
                      self_report=("I usually answer before checking my capacity." if kind == "self_report" else None),
                      domain=None, recorded_on=day,
                      citations=(Citation(entry_id=entry, entry_date=day,
                                          text=text + (" I usually answer before checking my capacity."
                                                       if kind == "self_report" else "")),))
    raw = episode.as_dict()
    return account_fingerprint(raw), raw


def definition() -> Definition:
    return Definition(context_predicate="Someone awaits an answer",
                      response_predicate="I agree before checking capacity",
                      title="Answering before checking capacity")


def membership(key: str, aid: str, context: str = "present", response: str = "present",
               relation: str = "linked") -> Membership:
    return Membership(dynamic_id=key, account_id=aid, context_decision=context,
                      response_decision=response, relation_decision=relation,
                      refs=[QuoteRef(account_id=aid, field="situation", citation_index=0)])


def pair(a: str, b: str, decision: str) -> PairDecision:
    return PairDecision(left_account_id=a, right_account_id=b, decision=decision,
                        refs=[QuoteRef(account_id=aid, field="situation", citation_index=0)
                              for aid in (a, b)] if decision != "unclear" else [])


def draft(accounts: dict[str, dict], rows: list[Membership], pairs: list[PairDecision]) -> DiscoveryDraft:
    d = definition()
    key = definition_key(d)
    validated = validate_matrix([d], accounts, rows)
    groups, assigned = partition_events(key, validated, pairs, accounts)
    groups, independent = count_independent(groups, pairs, accounts)
    return DiscoveryDraft(episodes=accounts, definitions=[d], memberships=assigned,
                          pair_decisions=pairs, groups={key: groups},
                          independent_group_ids={key: independent}, counts={"checkedPairs": len(rows)})


def test_silence_does_not_become_exception_and_matrix_is_all_or_nothing():
    d = definition()
    key = definition_key(d)
    a, raw_a = account(1)
    b, raw_b = account(2, actor="other")
    accounts = {a: raw_a, b: raw_b}
    assert derive_role("present", "unclear", "unclear") == "unclear"
    assert derive_role("present", "absent", "linked") == "exception"
    assert derive_role("absent", "present", "linked") == "response_elsewhere"
    assert derive_role("present", "present", "unclear") == "unclear"
    rows = validate_matrix([d], accounts, [membership(key, a), membership(key, b)])
    assert [r.role for r in rows] == ["support", "unclear"]
    for bad in ([membership(key, a)], [membership(key, a), membership(key, a)],
                [membership(key, a), membership("foreign", b)]):
        with pytest.raises(ValueError, match="membership"):
            validate_matrix([d], accounts, bad)
    with pytest.raises(ValidationError):
        Membership.from_dict({**membership(key, a).as_dict(), "relationDecision": "maybe"})


def test_retelling_triangle_poison_and_unknown_pair_cannot_create_recurring_pattern():
    ids, accounts = zip(*(account(n) for n in (1, 2, 3, 4)))
    sources = dict(zip(ids, accounts))
    key = definition_key(definition())
    a, b, c, independent = ids
    pairs = [pair(a, b, "same_event"), pair(b, c, "same_event"),
             pair(a, c, "distinct_events"), pair(a, independent, "distinct_events"),
             pair(b, independent, "distinct_events"), pair(c, independent, "distinct_events")]
    result = draft(sources, [membership(key, aid) for aid in ids], pairs)
    groups = result.groups[key]
    assert len(groups) == 4
    assert {g.id for g in groups if g.independence_uncertain} == {a, b, c}
    assert len(result.independent_group_ids[key]) == 2  # not three via contradictory links
    assert evidence_state(groups, [], sources) == "emerging"
    result_unknown = draft(sources, [membership(key, aid) for aid in ids],
                           [p if independent not in (p.left_account_id, p.right_account_id)
                            else pair(p.left_account_id, p.right_account_id, "unclear")
                            for p in pairs])
    assert len(result_unknown.independent_group_ids[key]) == 1
    assert evidence_state(result_unknown.groups[key], [], sources) is None


def test_three_checked_distinct_outcome_free_events_can_be_recurring():
    ids, raw = zip(*(account(n) for n in (10, 20, 30)))
    sources = dict(zip(ids, raw))
    key = definition_key(definition())
    result = draft(sources, [membership(key, aid) for aid in ids],
                   [pair(ids[0], ids[1], "distinct_events"),
                    pair(ids[0], ids[2], "distinct_events"),
                    pair(ids[1], ids[2], "distinct_events")])
    assert evidence_state(result.groups[key], [], sources) == "recurring"
    assert len(result.independent_group_ids[key]) == 3
    assert all(ep["immediateOutcome"] is None and ep["laterOutcome"] is None
               for ep in sources.values())


def test_cross_dynamic_insight_needs_four_mutually_checked_distinct_events():
    ids, raw = zip(*(account(n) for n in (11, 12, 13, 14, 15)))
    sources = dict(zip(ids, raw))
    first_four = ids[:4]
    checked = [pair(a, b, "distinct_events") for i, a in enumerate(first_four)
               for b in first_four[i + 1:]]
    key = definition_key(definition())
    result = draft(sources, [membership(key, aid) for aid in ids], checked)
    groups = [g for g in result.groups[key] if g.id in first_four]
    # A pair of dynamics may have two independent events each, yet still share
    # an occasion or lack a cross-dynamic distinction.
    assert mutually_independent(groups, checked, sources)
    assert not mutually_independent(groups, checked[:-1], sources)
    assert not mutually_independent([*groups[:3], groups[0]], checked, sources)
    bridge = [pair(ids[0], ids[4], "same_event"),
              pair(ids[4], ids[2], "same_event")]
    assert not mutually_independent(groups, [*checked, *bridge], sources)


def test_mixed_retellings_do_not_count_on_both_sides():
    a, raw_a = account(1)
    b, raw_b = account(2)
    c, raw_c = account(3)
    sources = {a: raw_a, b: raw_b, c: raw_c}
    key = definition_key(definition())
    result = draft(sources, [membership(key, a), membership(key, b, response="absent"),
                             membership(key, c)],
                   [pair(a, b, "same_event"), pair(a, c, "distinct_events"),
                    pair(b, c, "distinct_events")])
    mixed = next(g for g in result.groups[key] if set(g.account_ids) == {a, b})
    assert mixed.role == "mixed"
    assert not mixed.independently_countable
    assert result.independent_group_ids[key] == [c]
    assert evidence_state(result.groups[key], [], sources) is None


def test_range_preserves_out_of_range_bridge_and_owner_no_excludes_not_contrasts():
    a, raw_a = account(1, day=D - timedelta(days=8))
    bridge, raw_bridge = account(2, day=D - timedelta(days=100))
    b, raw_b = account(3, day=D - timedelta(days=3))
    c, raw_c = account(4, day=D - timedelta(days=1))
    sources = {a: raw_a, bridge: raw_bridge, b: raw_b, c: raw_c}
    key = definition_key(definition())
    result = draft(sources, [membership(key, aid) for aid in sources],
                   [pair(a, bridge, "same_event"), pair(bridge, b, "same_event"),
                    pair(a, b, "unclear"), pair(a, c, "distinct_events"),
                    pair(bridge, c, "distinct_events"), pair(b, c, "distinct_events")])
    projected = project_range(result, "30d", D)
    assert bridge not in projected.episodes
    shared = next(g for g in projected.groups[key] if {a, b} <= set(g.account_ids))
    assert shared.id == min(a, b, bridge)  # fixed all-archive ID, not rekeyed for window
    assert len(projected.independent_group_ids[key]) == 2
    corrected = project_range(result, "30d", D, {(key, c): "no"})
    assert len(corrected.independent_group_ids[key]) == 1
    assert next(g for g in corrected.groups[key] if c in g.account_ids).role == "unclear"
    assert not any(g.role == "exception" for g in corrected.groups[key])
    assert next(m for m in corrected.memberships if m.account_id == c).excluded
    assert evidence_state(corrected.groups[key], [], corrected.episodes) is None
    restored = project_range(result, "30d", D, {(key, c): None})
    assert len(restored.independent_group_ids[key]) == 2


def test_owner_report_is_not_three_events_and_no_inferred_outcome():
    aid, raw = account(1, kind="self_report")
    key = definition_key(definition())
    result = draft({aid: raw}, [membership(key, aid)], [])
    assert result.groups[key] == []
    assert evidence_state([], [aid], result.episodes) == "owner_described"
    assert evidence_state([], [], result.episodes) is None
    assert raw["immediateOutcome"] is None and raw["laterOutcome"] is None


def test_unchecked_pair_stays_unknown_and_incomplete_group_partition_is_rejected():
    a, raw_a = account(1)
    b, raw_b = account(2)
    key = definition_key(definition())
    result = draft({a: raw_a, b: raw_b}, [membership(key, a), membership(key, b)], [])
    assert len(result.independent_group_ids[key]) == 1
    with pytest.raises(ValidationError, match="incomplete event group partition"):
        DiscoveryDraft.from_dict({**result.as_dict(), "groups": {key: [result.groups[key][0].as_dict()]},
                                  "independentGroupIds": {key: [result.groups[key][0].id]}})

def test_stored_independence_claim_cannot_override_unknown_event_relationship():
    a, raw_a = account(1)
    b, raw_b = account(2)
    key = definition_key(definition())
    result = draft({a: raw_a, b: raw_b}, [membership(key, a), membership(key, b)], [])
    forged = result.as_dict()
    forged["groups"][key][1]["independentlyCountable"] = True
    forged["independentGroupIds"][key].append(result.groups[key][1].id)
    with pytest.raises(ValidationError, match="disagree with checked pairs"):
        DiscoveryDraft.from_dict(forged)


def test_serialized_draft_strict_refs_and_owner_bound_identity():
    aid, raw = account(1)
    key = definition_key(definition())
    result = draft({aid: raw}, [membership(key, aid)], [])
    assert DiscoveryDraft.from_dict(result.as_dict()) == result
    assert bind_dynamic_ids(result, 7)[key] == dynamic_id(7, definition())
    assert dynamic_id(7, definition()) != dynamic_id(8, definition())
    with pytest.raises(ValidationError):
        DiscoveryDraft.from_dict({**result.as_dict(), "legacyLabels": []})
    ref = QuoteRef(account_id=aid, field="situation", citation_index=0)
    field_checks = FieldChecks(account_id=aid, checks=[FieldCheck(field="situation", verdict="supported", refs=[ref]),
                                                       FieldCheck(field="response", verdict="supported", refs=[ref.model_copy(update={"field": "response"})])])
    validate_field_checks(Episode.from_dict(raw), field_checks)
    with pytest.raises(ValueError, match="field checks"):
        validate_field_checks(Episode.from_dict(raw), FieldChecks(account_id=aid, checks=field_checks.checks[:1]))
    clause = GroundedClause(text="I answered before checking capacity", refs=[ref])
    assert claim_hash({"observation": clause.as_dict(), "feedback": "yes", "lensMatches": []}) == claim_hash({"observation": clause.as_dict(), "feedback": "no", "lensMatches": ["editorial"]})
    assert snapshot_hash({"feedback": "yes"}) != snapshot_hash({"feedback": "no"})
