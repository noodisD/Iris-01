"""Reading a whole archive without losing what makes a reading trustworthy.

One pass over 110K tokens answers about the average of a life rather than about
what recurs in it, so the archive is read in passes. That introduces two ways to
go wrong, and both have precedent.

A pattern noticed in several passes comes back several times, in slightly
different words. Left alone that is exactly how the earlier system produced
thirteen near-identical "breakthroughs" in two days — restatement reading as
findings.

And reading two stores at once means ids stop being unique: on the real archive
15 staged import items share a number with a reflection. A quote checked against
whichever row happened to share the number would let an invented citation pass
by coincidence, which is the one thing verification exists to prevent.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import date

import pytest

from agent.constants import OBSERVATION_CHARS_PER_TOKEN
from agent.observations import Citation, Observation, chunk_entries, consolidate


def _entry(i, chars, source="reflection", day=None):
    return {"id": i, "source_type": source, "content": "w" * chars,
            "date": day or date(2026, 1, 1)}


def _observation(claim, citations, span=(date(2026, 1, 1), date(2026, 3, 1))):
    return Observation(claim=claim, citations=tuple(citations), span_start=span[0],
                       span_end=span[1], entries_read=len(citations), confidence_level="low")


def _cite(entry_id, text, source="reflection", day=date(2026, 1, 1)):
    return Citation(entry_id=entry_id, entry_date=day, text=text, source_type=source)


# --- passes small enough to read closely --------------------------------------

def test_a_chunk_stays_within_its_budget():
    budget = 100
    entries = [_entry(i, 30 * OBSERVATION_CHARS_PER_TOKEN) for i in range(10)]
    for chunk in chunk_entries(entries, budget_tokens=budget):
        cost = sum(len(e["content"]) // OBSERVATION_CHARS_PER_TOKEN for e in chunk)
        assert cost <= budget or len(chunk) == 1


def test_every_entry_reaches_exactly_one_pass():
    """Splitting the archive must not quietly drop or duplicate writing."""
    entries = [_entry(i, 40 * OBSERVATION_CHARS_PER_TOKEN) for i in range(17)]
    chunks = chunk_entries(entries, budget_tokens=100)

    seen = [e["id"] for chunk in chunks for e in chunk]
    assert sorted(seen) == list(range(17))
    assert len(seen) == len(set(seen))


def test_an_entry_larger_than_the_budget_is_still_read():
    """One transcript runs to 22,420 characters. It gets its own pass rather
    than being skipped for not fitting."""
    entries = [_entry(1, 10), _entry(2, 500 * OBSERVATION_CHARS_PER_TOKEN), _entry(3, 10)]
    chunks = chunk_entries(entries, budget_tokens=100)

    assert [e["id"] for chunk in chunks for e in chunk] == [1, 2, 3]
    assert any(len(c) == 1 and c[0]["id"] == 2 for c in chunks)


def test_an_empty_archive_yields_no_passes():
    assert chunk_entries([]) == []


# --- the same finding, noticed twice ------------------------------------------

def test_observations_sharing_an_entry_within_a_pass_become_one():
    """What merging actually does: join observations that cite the same entry.

    This test used to claim it covered "two passes noticing one pattern", using a
    citation shared between them. Passes are disjoint and each observation is
    verified only against its own chunk's entries, so two passes can never share
    a citation — the scenario could not occur, the test passed anyway, and it was
    read as evidence that cross-pass consolidation worked. It does not exist yet.
    """
    shared = _cite(1, "I went all in on the opening I was most certain about")
    first = _observation("Certainty and boldness appeared together", [shared, _cite(2, "doubled down again")])
    second = _observation("The boldest moves sat alongside the strongest certainty",
                          [shared, _cite(3, "doubled the attack")])

    merged = consolidate([first, second])

    assert len(merged) == 1, "observations citing one entry are joined"
    assert merged[0].claim == second.claim, "the longest claim survives — by length, not by meaning"


@pytest.mark.xfail(reason="cross-pass consolidation is not built; see Package 3", strict=True)
def test_the_same_finding_restated_in_two_passes_becomes_one():
    """The behaviour consolidation was described as having, and does not.

    Disjoint passes produce disjoint citations, and merging keys on citation
    overlap, so the same finding noticed twice stays two findings. Recorded as a
    failing test rather than a comment so that building it flips this to green.
    """
    first = _observation("Certainty and boldness appeared together", [_cite(1, "a"), _cite(2, "b")])
    second = _observation("Certainty and boldness appeared together", [_cite(7, "c"), _cite(8, "d")])

    assert len(consolidate([first, second])) == 1


def test_merging_does_not_depend_on_the_order_observations_arrive():
    """A,B,C used to yield one group and A,C,B two, because grouping joined an
    observation to the first group it touched and stopped — so a bridging
    observation did not unite the groups it connected. The partition is now
    connected components, which does not depend on which pass finished first."""
    a = _observation("A", [_cite(1, "a"), _cite(2, "b")])
    b = _observation("B", [_cite(2, "b"), _cite(3, "c")])
    c = _observation("C", [_cite(3, "c"), _cite(4, "d")])

    assert len(consolidate([a, b, c])) == len(consolidate([a, c, b]))


def test_merging_keeps_every_citation():
    shared = _cite(1, "I went all in on the opening I was most certain about")
    merged = consolidate([
        _observation("A", [shared, _cite(2, "doubled down again")]),
        _observation("A longer claim about the same thing", [shared, _cite(3, "doubled the attack")]),
    ])[0]

    assert {c.entry_id for c in merged.citations} == {1, 2, 3}, "evidence is pooled, not discarded"


def test_a_citation_is_not_counted_twice():
    same = _cite(1, "I went all in on the opening I was most certain about")
    merged = consolidate([_observation("A", [same, _cite(2, "b")]),
                          _observation("A bit longer", [same, _cite(2, "b")])])[0]
    assert len(merged.citations) == 2


def test_findings_with_no_writing_in_common_stay_separate():
    a = _observation("Sleep and the following morning", [_cite(1, "slept badly"), _cite(2, "tired")])
    b = _observation("Boldness and certainty", [_cite(3, "all in"), _cite(4, "doubled down")])
    assert len(consolidate([a, b])) == 2


def test_pooled_evidence_can_raise_confidence():
    """Two entries is tentative; four across months is not. Merging should
    reflect the evidence that now stands behind the claim."""
    a = _observation("A", [_cite(1, "one", day=date(2026, 1, 1)),
                           _cite(2, "two", day=date(2026, 1, 2))])
    b = _observation("A longer version", [_cite(2, "two", day=date(2026, 1, 2)),
                                          _cite(3, "three", day=date(2026, 3, 1)),
                                          _cite(4, "four", day=date(2026, 4, 1))])
    merged = consolidate([a, b])[0]

    assert len({c.key for c in merged.citations}) == 4
    assert merged.confidence_level == "high"
    assert merged.span_start == date(2026, 1, 1) and merged.span_end == date(2026, 4, 1)


def test_consolidating_nothing_yields_nothing():
    assert consolidate([]) == []


# --- two stores, overlapping ids ----------------------------------------------

def test_the_same_number_in_two_stores_is_two_different_entries():
    """Reflection 160 and staged item 160 are unrelated pieces of writing."""
    reflection = _cite(160, "a sentence from the journal", source="reflection")
    staged = _cite(160, "a sentence from a recording", source="import_item")

    assert reflection.key != staged.key
    merged = consolidate([_observation("A", [reflection, _cite(1, "x")]),
                          _observation("B", [staged, _cite(2, "y")])])
    assert len(merged) == 2, "an id collision must not merge unrelated findings"


def test_a_citation_says_whether_it_can_become_evidence():
    """A staged recording has no date, so it can be quoted and never counted."""
    assert _cite(1, "from the journal").as_dict()["citable"] is True
    assert _cite(1, "from a recording", source="import_item").as_dict()["citable"] is False
