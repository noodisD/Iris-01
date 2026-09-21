"""What an account of an occasion has to survive before it counts as one.

The reader IRIS has finds subjects that recur. It cannot find that two accounts
have the same *shape* — a demand on attention, something arriving while it is
occupied, and what followed — because a claim with quotations has no shape in
it. This prototype extracts a frame instead: who, whether it happened, the
situation, what it demanded, what came in, what they did, what followed.

The acceptance case is the one that prompted it, in invented form. Someone
describes one occasion while learning something unfamiliar, and then draws a
connection to a different activity. The correct behaviour is not to report a
pattern: it is to keep the account, keep the connection as *theirs*, and say
plainly that only one of the two has an occasion behind it.

The three refusals below are the ways this goes wrong quietly: a friend's
experience becoming the owner's, an intention becoming an event, and one
occasion retold twice becoming two.

Every entry here is invented.
"""

from __future__ import annotations

from datetime import date

from agent.episodes import Episode, EpisodeReader, tally, verified_episodes

LESSON = ("Third cycling lesson on the busy road. I was so taken up with the gears and "
          "the clipless pedals that when the instructor said to take the second exit I "
          "only heard the word second and had to ask again at the roundabout.")
CHESS = ("Blitz tournament tonight. I had decided the opening repertoire before I sat "
         "down, and when the clock got low I did not have to think about what to play, "
         "only about the position.")
FRIEND = ("Marek told me he missed his turning on the ring road because he was busy "
          "with the sat nav.")
PLAN = ("Next week I will decide the whole repertoire in advance so there is nothing "
        "left to work out with the clock running.")

ENTRIES = [
    {"id": 1, "date": date(2026, 9, 15), "content": LESSON, "source_type": "reflection"},
    {"id": 2, "date": date(2026, 9, 17), "content": CHESS, "source_type": "reflection"},
    {"id": 3, "date": date(2026, 9, 18), "content": FRIEND, "source_type": "reflection"},
    {"id": 4, "date": date(2026, 9, 19), "content": PLAN, "source_type": "reflection"},
]


def _episode(**over):
    base = {
        "actor": "self", "modality": "happened",
        "situation": "a cycling lesson on a busy road",
        "demand": "managing the gears and the pedals",
        "information": "an instruction to take the second exit",
        "response": "asked for the instruction again at the roundabout",
        "outcome": "only part of the instruction was taken in",
        "quotes": [{"entryId": 1, "sourceType": "reflection",
                    "text": "I only heard the word second and had to ask again at the roundabout"}],
    }
    return {**base, **over}


# --- what is kept ---------------------------------------------------------------

def test_an_account_of_one_occasion_is_kept_with_its_words():
    kept = verified_episodes([_episode()], ENTRIES)

    assert len(kept) == 1
    episode = kept[0]
    assert (episode.actor, episode.modality) == ("self", "happened")
    assert episode.is_complete, "every part of the frame was stated"
    assert episode.occurred_on == date(2026, 9, 15)
    assert episode.citations[0].entry_id == 1


def test_a_missing_part_is_absent_rather_than_completed():
    """"Usually" is not evidence. An account that does not say what followed
    is an account with no outcome, not one whose outcome can be assumed."""
    kept = verified_episodes([_episode(outcome=None, demand=None)], ENTRIES)

    assert kept[0].outcome is None and kept[0].demand is None
    assert not kept[0].is_complete, "and it cannot be compared on its shape"


# --- what is refused ------------------------------------------------------------

def test_someone_elses_experience_does_not_become_the_owners():
    """The quote is real and the account is accurate — about Marek. Recorded as
    the owner's, it would be evidence of something they never did."""
    theirs = _episode(
        actor="other", situation="a drive on the ring road",
        demand="working the sat nav", information="the turning",
        response="missed the turning", outcome="had to go round again",
        quotes=[{"entryId": 3, "sourceType": "reflection",
                 "text": "Marek told me he missed his turning on the ring road"}])

    kept = verified_episodes([theirs], ENTRIES)

    assert len(kept) == 1
    assert kept[0].actor == "other"
    assert tally(kept)["comparable"] == 0, "not the owner's occasion, so not comparable"


def test_an_intention_is_not_an_event():
    """A record of plans read as a record of behaviour is the oldest way this
    sort of reader flatters someone."""
    intention = _episode(
        modality="planned", situation="a tournament next week",
        demand=None, information=None,
        response="decide the repertoire in advance", outcome=None,
        quotes=[{"entryId": 4, "sourceType": "reflection",
                 "text": "Next week I will decide the whole repertoire in advance"}])

    kept = verified_episodes([intention], ENTRIES)

    assert kept[0].modality == "planned"
    assert tally(kept)["happened"] == 0
    assert tally(kept)["comparable"] == 0


def test_a_quote_that_is_not_in_the_entry_drops_the_whole_account():
    invented = _episode(quotes=[{"entryId": 1, "sourceType": "reflection",
                                 "text": "I always lose track when I am concentrating"}])

    assert verified_episodes([invented], ENTRIES) == []


def test_an_account_attributed_to_the_wrong_entry_is_refused():
    """The words exist — in a different entry."""
    misplaced = _episode(quotes=[{"entryId": 2, "sourceType": "reflection",
                                  "text": "I only heard the word second"}])

    assert verified_episodes([misplaced], ENTRIES) == []


def test_an_account_that_explains_itself_is_refused():
    """The frame records what happened. "Because" is an interpretation, and the
    owner's interpretation is theirs to make (agent/narrative_policy.py)."""
    explained = _episode(outcome="missed the instruction because attention was used up")

    assert verified_episodes([explained], ENTRIES) == []


def test_an_account_with_no_situation_or_no_response_is_a_remark():
    assert verified_episodes([_episode(situation=None)], ENTRIES) == []
    assert verified_episodes([_episode(response=None)], ENTRIES) == []


# --- the acceptance case --------------------------------------------------------

class _Reader:
    """A model that answers with whatever the test scripts, once per chunk."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.asked = 0

    def chat(self, messages, system_prompt, **kwargs):
        self.asked += 1
        import json
        reply = self.replies.pop(0) if self.replies else {"episodes": []}
        return json.dumps(reply)


def test_one_occasion_and_a_connection_are_not_a_pattern():
    """The case this was built for.

    The archive holds an account of one occasion, and — in a different entry
    about a different activity — the owner's own connection to it. What IRIS
    may say is: here is the occasion, here is your connection, and there is no
    second occasion behind it yet. What it may not say is that anything
    recurs, that one thing caused another, or that this is how the owner is.

    The counts are what say so: one comparable episode cannot make a pattern,
    and this is the number a comparison pass would have to look at first.
    """
    reader = EpisodeReader(1, intelligence=_Reader({"episodes": [_episode()]}))

    episodes = reader.read(ENTRIES)
    counts = tally(episodes)

    assert counts["episodes"] == 1
    assert counts["comparable"] == 1, "the cycling occasion, and only it"
    assert counts["comparable"] < 2, (
        "a shape shared by two occasions needs two occasions; with one, the "
        "honest answer is the account and the owner's own connection to it")


def test_a_pass_that_returns_nothing_usable_returns_nothing():
    """Fail closed, like every other reader here: a model that answers badly
    produces no accounts rather than unverified ones."""
    assert EpisodeReader(1, intelligence=_Reader("not json")).read(ENTRIES) == []
    assert EpisodeReader(1, intelligence=None).read(ENTRIES) == []


def test_nothing_is_written_anywhere():
    """This reader is a measurement. It has no table, no candidate, no card —
    so it cannot become a surface by accident before anyone decides it should."""
    import inspect

    import agent.episodes as module

    source = inspect.getsource(module)
    for writer in ("INSERT", "UPDATE", "db.create", "promote(", "add_theme"):
        assert writer not in source, f"the prototype writes something: {writer}"


def test_an_episode_states_itself_flatly_for_the_support_check():
    episode = verified_episodes([_episode()], ENTRIES)[0]
    claim = episode.as_claim()

    assert claim.startswith("On one occasion:")
    assert "because" not in claim and "should" not in claim


def test_the_frame_is_what_a_behaviour_claim_was_missing():
    """ADR-0016 refuses to confirm that something *happened* because actor,
    event identity, modality and time are unchecked. The frame carries all
    four, which is why this prototype exists."""
    episode = verified_episodes([_episode()], ENTRIES)[0]

    assert episode.actor and episode.modality
    assert episode.occurred_on is not None
    assert episode.citations, "and the sentences it rests on"
    assert isinstance(episode, Episode)


# --- what makes two accounts comparable ------------------------------------------

def test_an_account_that_says_what_followed_can_be_compared():
    """Requiring every part admitted 19 of 86 accounts on the real archive,
    because `information` — what arrived while attention was occupied — is the
    heart of one shape and absent from others. Situation, response and outcome
    are what two accounts need to be set beside each other; the rest are
    markers they may or may not share."""
    from agent.episodes import comparable

    no_cue = verified_episodes([_episode(demand=None, information=None)], ENTRIES)[0]

    assert not no_cue.is_complete
    assert no_cue.has_shape
    assert comparable([no_cue]) == [no_cue]
    assert no_cue.markers == ()


def test_an_account_with_no_outcome_has_nothing_to_agree_with():
    silent = verified_episodes([_episode(outcome=None)], ENTRIES)[0]

    assert not silent.has_shape
    from agent.episodes import comparable
    assert comparable([silent]) == []


def test_an_explanation_is_kept_as_theirs_and_apart_from_what_happened():
    """The owner's own account of why is what a proposed connection might
    agree with or extend — and what decides whether it is new to them."""
    explained = verified_episodes([_episode(
        explanation="I think the unfamiliar actions were using up the attention",
        domain="cycling")], ENTRIES)[0]

    assert explained.explanation.startswith("I think")
    assert explained.domain == "cycling"
    assert explained.explanation not in explained.situation


def test_an_episode_survives_a_round_trip_through_the_cache():
    """A cached run is read back as the same accounts, quotes included: the
    archive is read once and every later experiment runs against that."""
    original = verified_episodes([_episode(domain="cycling")], ENTRIES)[0]

    restored = Episode.from_dict(original.as_dict())

    assert restored == original
