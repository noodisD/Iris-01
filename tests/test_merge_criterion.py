"""How much two findings must have in common before they are one finding.

Three attempts at this rule, and the first two were wrong in opposite ways.

Greedy first-match grouping joined an observation to the first group it touched
and stopped, so the partition depended on which pass finished first. Replacing it
with connected components fixed the order-dependence and installed single-linkage
— the very algorithm a review had wrongly *named* when describing the original.
On this archive that matters, because the voice transcripts run to 22,000
characters and several unrelated findings legitimately quote the same one. One
shared citation was enough to glue a claim about one subject to quotes about
two unrelated ones.

Complete linkage is not the remedy, which is the part worth recording. In a group
bridged by one multi-topic entry, *every* pair genuinely shares that entry, so
complete linkage's condition is satisfied and the group forms anyway. What
separates a shared bridge from a shared subject is how much of each finding's
evidence the other one covers — a ratio, not adjacency.

Each case below has a correct answer by construction (ADR-0009): the citations
are written here, so what should group is not a matter of opinion.
"""

from __future__ import annotations

from datetime import date

from agent.constants import OBSERVATION_MERGE_OVERLAP
from agent.observations import Citation, Observation, consolidate


def _obs(claim, keys):
    """A finding citing exactly these entries. `keys` are (source_type, id)."""
    return Observation(
        claim=claim,
        citations=tuple(
            Citation(entry_id=i, entry_date=date(2026, 1, 1 + (i % 27)),
                     text=f"a quoted sentence from {t} {i}", source_type=t)
            for t, i in keys),
        span_start=date(2026, 1, 1), span_end=date(2026, 3, 1),
        entries_read=10, confidence_level="low")


# --- what must not merge --------------------------------------------------------

def test_one_long_recording_does_not_glue_unrelated_findings():
    """The live failure. A 22,000-character transcript is cited by findings about
    three unrelated subjects; they are not one pattern."""
    bridge = ("import_item", 90)
    findings = [
        _obs("Gardening and the allotment recurred", [bridge, ("reflection", 1)]),
        _obs("Choir rehearsal appears as a practice", [bridge, ("reflection", 2)]),
        _obs("Language lessons come up repeatedly", [bridge, ("reflection", 3)]),
    ]
    assert len(consolidate(findings)) == 3


def test_a_chain_through_different_entries_is_not_one_finding():
    """A shares an entry with B, B with C, A with nothing of C's. Chaining these
    is what ADR-0014 abandoned for themes."""
    findings = [
        _obs("First", [("reflection", 1), ("reflection", 2)]),
        _obs("Second", [("reflection", 2), ("reflection", 3)]),
        _obs("Third", [("reflection", 3), ("reflection", 4)]),
    ]
    assert len(consolidate(findings)) == 3


def test_findings_with_nothing_in_common_stay_apart():
    findings = [
        _obs("Sleep and the morning after", [("reflection", 1), ("reflection", 2)]),
        _obs("Boldness and certainty", [("reflection", 3), ("reflection", 4)]),
    ]
    assert len(consolidate(findings)) == 2


# --- what must merge ------------------------------------------------------------

def test_two_findings_over_the_same_evidence_are_one():
    same = [("reflection", 1), ("reflection", 2)]
    findings = [_obs("Certainty and boldness appeared together", same),
                _obs("The boldest moves sat with the strongest certainty", same)]
    assert len(consolidate(findings)) == 1


def test_substantial_overlap_merges():
    """Two thirds shared, one entry each of their own."""
    findings = [
        _obs("First", [("reflection", 1), ("reflection", 2), ("reflection", 3)]),
        _obs("Second and longer", [("reflection", 1), ("reflection", 2), ("reflection", 4)]),
    ]
    assert len(consolidate(findings)) == 1


def test_identical_wording_merges_across_disjoint_passes():
    """Passes share no citations, so overlap can never reach across them. Two
    identical sentences are the same sentence — not a judgement about meaning."""
    claim = "Certainty and boldness appeared together"
    findings = [_obs(claim, [("reflection", 1), ("reflection", 2)]),
                _obs(claim, [("reflection", 7), ("reflection", 8)])]
    assert len(consolidate(findings)) == 1


# --- the rule itself ------------------------------------------------------------

def test_the_threshold_is_a_ratio_not_a_count():
    """One shared entry out of two is half; one out of ten is not. A big finding
    and a small one sharing a single entry are not the same finding."""
    small = [("reflection", 1), ("reflection", 2)]
    large = [("reflection", 1)] + [("reflection", i) for i in range(10, 19)]
    assert len(consolidate([_obs("Small", small), _obs("Large", large)])) == 2


def test_the_result_does_not_depend_on_arrival_order():
    a = _obs("A", [("reflection", 1), ("reflection", 2)])
    b = _obs("B", [("reflection", 2), ("reflection", 3)])
    c = _obs("C", [("reflection", 3), ("reflection", 4)])
    assert len(consolidate([a, b, c])) == len(consolidate([a, c, b])) == \
           len(consolidate([c, b, a]))


def test_the_threshold_is_stated_once():
    assert 0 < OBSERVATION_MERGE_OVERLAP <= 1


def test_merging_still_pools_every_citation():
    same = [("reflection", 1), ("reflection", 2)]
    merged = consolidate([_obs("First", same), _obs("Second and longer", same)])[0]
    assert {c.entry_id for c in merged.citations} == {1, 2}
    assert merged.claim == "Second and longer", "the fullest statement survives"


def test_consolidating_nothing_is_nothing():
    assert consolidate([]) == []
