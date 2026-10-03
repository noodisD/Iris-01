"""A therapy session: only the owner's own turns can become evidence (ADR-0028).

Every line of every transcript below is invented.
"""

from __future__ import annotations

from datetime import date

from agent import sessions
from agent.episodes import verified_episodes
from agent.observations import verify_citations

TRANSCRIPT = """# Session two, notes from the transcriber
Speakers marked where the voices were clear.

**[00:00:05] Ann:**
Last week I kept postponing the call to my landlord because I expected an argument.

**[00:00:21] Counsellor:**
What happened when you finally called him about the heating?

**[00:00:30] Ann:**
He agreed to fix the heating straight away.

**[00:00:41] Ann:**
I felt silly for waiting so long.

**[00:00:52] Counsellor (unsure):**
So the waiting cost more than the call itself did.

**[00:01:03] Speaker unsure:**
Yes, that is how it went for me.
"""

OWNER_FIRST = "Last week I kept postponing the call to my landlord because I expected an argument."
OWNER_SECOND = "He agreed to fix the heating straight away. I felt silly for waiting so long."


def _content() -> str:
    found, _ = sessions.segments(TRANSCRIPT)
    return sessions.compose(found, kind="therapy", started="2026-09-30T18:00", language="en",
                            owner="Ann", therapist="Counsellor")


def _entry(entry_id: int = 7) -> dict:
    return {"id": entry_id, "source_type": "reflection", "date": date(2026, 9, 30),
            "content": _content(), "content_format": "session"}


def _event(quote: str, situation: str, response: str) -> dict:
    return {"actor": "self", "recordKind": "event", "situation": situation, "response": response,
            "quotes": [{"entryId": 7, "sourceType": "reflection", "text": quote}]}


# --- the format ----------------------------------------------------------------

def test_a_transcript_is_read_as_labelled_segments_without_its_title():
    found, preamble = sessions.segments(TRANSCRIPT)
    assert preamble == 2, "the title and the note are nobody's words"
    assert [segment.label for segment in found] == [
        "Ann", "Counsellor", "Ann", "Ann", "Counsellor (unsure)", "Speaker unsure"]
    assert found[0].at == 5 and found[-1].at == 63
    assert found[0].text == OWNER_FIRST


def test_shorter_marker_styles_are_read_too():
    found, _ = sessions.segments("[01:02] Ann: Words on the same line as the marker.\n"
                                 "[01:09] Counsellor: And a reply to them.\n"
                                 "**[1:00:01] Ann:** Bold, with an hour.")
    assert [(s.at, s.label, s.text) for s in found] == [
        (62, "Ann", "Words on the same line as the marker."),
        (69, "Counsellor", "And a reply to them."),
        (3601, "Ann", "Bold, with an hour.")]


def test_one_speakers_consecutive_segments_become_one_turn_with_every_word_kept():
    session = sessions.read(_content())
    assert [turn.label for turn in session.turns] == [
        "Ann", "Counsellor", "Ann", "Counsellor (unsure)", "Speaker unsure"]
    assert session.turns[2].text == OWNER_SECOND
    content = _content()
    for turn in session.turns:
        assert content[turn.start:turn.end] == turn.text
    words = " ".join(segment.text for segment in sessions.segments(TRANSCRIPT)[0]).split()
    assert " ".join(turn.text for turn in session.turns).split() == words


def test_a_role_comes_from_the_exact_label_and_anything_else_is_unclear():
    session = sessions.read(_content())
    assert [turn.role for turn in session.turns] == [
        "owner", "therapist", "owner", "unclear", "unclear"]
    renamed = sessions.read(_content().replace("**[00:00:30] Ann:**", "**[00:00:30] ann:**"))
    assert renamed.turns[2].role == "unclear", "a label that is not exactly the owner's is not the owner"


def test_content_without_named_speakers_is_not_a_session():
    assert sessions.read("Just a journal entry.") is None
    assert sessions.read("---\ntitle: notes\n---\n\nText") is None


def test_the_import_screen_offers_a_guess_and_never_guesses_an_unsure_label():
    found, _ = sessions.segments(TRANSCRIPT)
    assert sessions.guess_roles(found) == ("Ann", "Counsellor")
    assert sessions.guess_language(TRANSCRIPT) == "en"
    assert sessions.guess_language("Zażółć gęślą jaźń, powiedziałem wczoraj.") == "pl"


def test_a_model_reads_every_turn_with_its_speaker_named():
    from agent.markdown_text import for_model

    rendered = for_model(_content(), "session")
    assert "Ann is the owner" in rendered and "Counsellor is the therapist" in rendered
    assert f"[00:00:05] Ann (owner): {OWNER_FIRST}" in rendered
    assert "[00:00:52] Counsellor (unsure) (speaker unclear):" in rendered
    assert "---" not in rendered and "**" not in rendered


def test_recalled_passages_keep_whole_turns_with_their_speakers():
    cut = sessions.passages(_content(), limit=200)
    assert len(cut) > 1
    for passage in cut:
        for line in passage.text.splitlines():
            assert line.startswith("[00:") and ("(owner):" in line or "(therapist):" in line
                                                or "(speaker unclear):" in line)
    assert "\n".join(p.text for p in cut).count("Ann (owner)") == 2


# --- evidence ------------------------------------------------------------------

def test_an_account_in_the_owners_turn_cites_that_whole_turn():
    found = verified_episodes([_event(
        "I kept postponing the call to my landlord because I expected an argument",
        "I expected an argument", "I kept postponing the call to my landlord")], [_entry()])
    assert len(found) == 1
    assert found[0].citations[0].text == OWNER_FIRST


def test_an_account_resting_on_the_therapists_words_is_not_kept():
    found = verified_episodes([_event(
        "What happened when you finally called him about the heating",
        "you finally called him", "called him about the heating")], [_entry()])
    assert found == []


def test_a_turn_whose_speaker_is_unclear_is_never_evidence():
    found = verified_episodes([{
        "actor": "self", "recordKind": "self_report", "selfReport": "that is how it went for me",
        "quotes": [{"entryId": 7, "sourceType": "reflection", "text": "Yes, that is how it went for me"}],
    }], [_entry()])
    assert found == []


def test_an_account_joining_two_of_the_owners_turns_is_not_kept():
    account = _event("I kept postponing the call to my landlord because I expected an argument",
                     "I expected an argument", "He agreed to fix the heating straight away")
    account["quotes"].append({"entryId": 7, "sourceType": "reflection",
                              "text": "He agreed to fix the heating straight away"})
    assert verified_episodes([account], [_entry()]) == []


def test_words_both_speakers_said_count_only_where_the_owner_said_them():
    found, _ = sessions.segments("**[00:00:01] Counsellor:**\nYou said the waiting was the hard part.\n\n"
                                 "**[00:00:09] Ann:**\nYes, the waiting was the hard part for me.\n")
    content = sessions.compose(found, kind="therapy", started="2026-09-30T18:00", language="en",
                               owner="Ann", therapist="Counsellor")
    held = sessions.owner_turn(content, "the waiting was the hard part")
    assert held is not None and held[0].label == "Ann"


def test_idea_quotes_from_a_session_must_be_the_owners():
    entry = _entry()
    ok = verify_citations([{"entryId": 7, "text": "I felt silly for waiting so long"}],
                          {("reflection", 7): entry})
    assert ok is not None and ok[0].text == "I felt silly for waiting so long"
    for quote in ("What happened when you finally called him",
                  "So the waiting cost more than the call itself did",
                  "Yes, that is how it went for me"):
        assert verify_citations([{"entryId": 7, "text": quote}], {("reflection", 7): entry}) is None


def test_an_idea_check_sees_the_turns_around_a_quote_not_the_whole_session():
    from agent.ideas import reader
    from agent.ideas.models import CITATION_STANCES

    STANCE = CITATION_STANCES[0]

    class Stances:
        def __init__(self):
            self.payload = None

        def chat(self, *, messages, **_):
            import json
            self.payload = json.loads(messages[0]["content"])
            return json.dumps({"quotes": [{"i": 0, "stance": STANCE}]})

    entry = _entry()
    citations = verify_citations([{"entryId": 7, "text": "I felt silly for waiting so long"}],
                                 {("reflection", 7): entry})
    model = Stances()
    reader.check_stances(model, "Waiting can cost more than acting", citations, {("reflection", 7): entry})
    context = model.payload["quotes"][0]["context"]
    assert "Counsellor (therapist): What happened" in context
    assert "Ann (owner): He agreed" in context
    assert "Speaker unsure" not in context, "only the turns either side"
