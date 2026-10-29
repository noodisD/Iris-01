"""Write the synthetic corpus for the chat eval (corpus_spec.md), and check it.

    uv run python evals/build_corpus.py

Everything here is invented: Mara Vell is nobody. The planted sentences are
named once below and used both in the entries and in gold.json, so a gold
label can never drift from the words it points at; the script then checks
that each one is found in its entry and that the absent topics are absent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / "corpus"

# --- planted sentences -------------------------------------------------------

P1 = {
    "e012": "Deadline week again, so I skipped my run this morning and stayed at the desk.",
    "e024": "I skipped the long run because the competition boards were due on Monday.",
    "e041": "Another deadline, another skipped run. I slept badly afterwards, which is what always happens when I miss one.",
    "e058": "I skipped the long run again for the hospital drawings.",
    "e072": "Deadline crunch, no running all week, and my sleep has been rubbish since.",
}
P1_SLEEP = {
    "e012": "I slept worse than usual that night.",
    "e024": "Slept badly, woke at four.",
}
P2 = {
    "e015": "At half past five on Friday Henrik asked if I could take the facade details over the weekend, and I said yes before I had even looked at my week.",
    "e033": "Friday, 5:40, Henrik again: could I cover the planning comments by Monday. I said yes straight away and only then remembered the move.",
    "e049": "Henrik caught me at the lift on Friday evening with one more revision, and I agreed before checking anything.",
    "e066": "Late Friday Henrik asked for the tender drawings by Tuesday and I said fine, then opened my calendar and saw I had no gap at all.",
}
P3 = {
    "e037": "Bad night, maybe three hours. I called Tomek before work and felt steadier afterwards.",
    "e061": "Slept terribly again. Rang Tomek on the walk to the office; after ten minutes with him I felt more level.",
}
P4 = "I go quiet when someone is angry with me. I just stop talking."
T1_COUNSELLOR = "It sounds like you avoid conflict at work."
T1_MARA = "I'm not sure that's it."
T11_COUNSELLOR = "I wonder whether you're burning out."
T3 = {
    "e009": "Coffee with Ines after the site visit, which was nice.",
    "e044": "Too much coffee today, I'm buzzing.",
    "e070": "No coffee at all this week and I didn't notice the difference.",
}
T5 = "The cello recital is coming up and I still can't get through the second page without stopping."
T6 = "On the way back from the station in April I turned my ankle on the kerb, and it was swollen for a week."
T7_SELF = "I always cancel plans when I'm tired."
T7_KEPT = {
    "e030": "Exhausted, but I still went to Ines's birthday dinner and stayed until eleven.",
    "e055": "Dead tired after the review, but I kept the cinema plan with Tomek and I'm glad I did.",
}
T9 = "Practised the Bach I keep stumbling over for forty minutes; the shifts in the middle are still a mess."
REASON_MOVE = "We're moving because the new flat is ten minutes from the studio and has a room for the cello."
T8_ANSWER = "Being near water calms me, and long walks with no destination."

# --- the journal ---------------------------------------------------------------

ENTRIES: list[tuple[str, str | None, str, str]] = [
    ("e001", "2026-03-01", "plain", "First day of March. Cleaned the drawing board and finally threw out the old trace paper. Quiet weekend, mostly reading."),
    ("e002", "2026-03-02", "plain", "Studio meeting about the library extension. Henrik wants three options by the end of the month. Lunch outside for the first time this year."),
    ("e003", "2026-03-03", "plain", "Ran 6 km along the canal before work. Legs heavy but it cleared my head."),
    ("e004", "2026-03-05", "plain", "Cello lesson. Ola says my bow arm is better but I rush the slow passages. Homework: scales and the first page, slowly."),
    ("e005", "2026-03-06", "plain", "Long day of model making. Cut my finger on the scalpel, nothing serious."),
    ("e006", "2026-03-08", "plain", "Tomek came over for dinner. He's thinking of changing jobs and talked about it for two hours. I mostly listened."),
    ("e007", "2026-03-09", "plain", "Ran 8 km. Felt good. Started thinking about whether to move flats this summer."),
    ("e008", "2026-03-11", "plain", "Rain all day. Worked on the stair detail for the library. Can't get the landing to sit right."),
    ("e009", "2026-03-12", "plain", f"{T3['e009']} The concrete pour went fine and the contractor was in a good mood for once."),
    ("e010", "2026-03-13", "markdown", "## Library extension, options\n\n- Option A: timber frame, cheapest\n- Option B: brick, matches the old wing\n- Option C: glass link, Henrik's favourite\n\nI like B but I think I'll lose that argument."),
    ("e011", "2026-03-15", "plain", "Cello practice, 30 minutes. Scales only. Boring but I can hear it helping."),
    ("e012", "2026-03-17", "plain", f"{P1['e012']} The options for the library are due Friday. {P1_SLEEP['e012']}"),
    ("e013", "2026-03-18", "plain", "Presented the three options to Henrik. He picked C, as expected. I argued for B for about a minute and then let it go."),
    ("e014", "2026-03-20", "plain", "Lighter day. Went for a run at lunch, 5 km, sun out."),
    ("e015", "2026-03-20", "plain", f"{P2['e015']} So much for the weekend."),
    ("e016", "2026-03-22", "plain", "Spent Sunday on the facade details. Done by four, then watched a film. Annoyed with myself more than with Henrik."),
    ("e017", "2026-03-24", "plain", "Viewed a flat on Lindenstraße. Too dark. The agent kept saying it had character."),
    ("e018", "2026-03-26", "plain", "Cello lesson. Ola gave me a new piece, a Bach suite movement. Lovely and much too hard."),
    ("e019", "2026-03-28", "plain", "Ran 10 km, longest this year. Slept like a stone."),
    ("e020", "2026-03-30", "plain", "Ines and I walked around the new park after work. She's starting at a bigger practice in May."),
    ("e021", "2026-04-01", "plain", "Viewed another flat, this one near the studio. Bright, a spare room, a bit small in the kitchen. I keep thinking about it."),
    ("e022", "2026-04-02", "plain", "Put in an application for the flat near the studio."),
    ("e023", "2026-04-04", "plain", "Quiet Saturday. Practised, read, cooked a proper meal for once."),
    ("e024", "2026-04-06", "plain", f"{P1['e024']} {P1_SLEEP['e024']} Boards went out on time though."),
    ("e025", "2026-04-08", "plain", "We got the flat! Moving at the end of May. Told Tomek and he offered to help carry things."),
    ("e026", "2026-04-09", "plain", f"{REASON_MOVE} I can walk to work and practise without the neighbours banging on the wall."),
    ("e027", "2026-04-11", "plain", "Ran by the canal, 7 km. A heron on the far bank the whole way."),
    ("e028", "2026-04-13", "plain", f"{T7_SELF} Cancelled drinks with the office crowd tonight because I could barely keep my eyes open."),
    ("e029", "2026-04-15", "plain", "Site meeting in the rain. The library contractor wants to change the window supplier. Henrik said no."),
    ("e030", "2026-04-17", "plain", f"{T7_KEPT['e030']} Didn't regret it."),
    ("e031", "2026-04-19", "plain", "Cello lesson. The Bach is slow going. Ola says to practise the hard bars backwards."),
    ("e032", "2026-04-21", "plain", "Started packing books. I own far too many architecture books I never open."),
    ("e033", "2026-04-24", "plain", f"{P2['e033']} I'll have to do the comments on Sunday and pack in the evenings."),
    ("e034", "2026-04-26", "plain", "Did the planning comments all Sunday. Packed two boxes. Tired."),
    ("e035", "2026-04-28", "plain", "Short run, 4 km, legs stiff. Took it easy."),
    ("e036", "2026-04-30", "plain", "End of April. The library is on site now and the office has gone quiet. Feels like a breath."),
    ("e037", "2026-05-02", "plain", f"{P3['e037']} He was making breakfast for his flatmate and told me about a terrible date. I laughed for the first time all week."),
    ("e038", "2026-05-04", "plain", "Ines started at the new practice. Sent her flowers."),
    ("e039", "2026-05-06", "plain", f"{T9} Ola says I'm overthinking the fingering."),
    ("e040", "2026-05-08", "markdown", "# Before the move\n\n- book the van for the 30th\n- cancel the internet at the old flat\n- give the spare key back to the landlord\n- pack the cello last\n- tell the post office the new address"),
    ("e041", "2026-05-11", "plain", f"{P1['e041']} The hospital competition is eating everything."),
    ("e042", "2026-05-13", "plain", "Practised scales on the balcony. A neighbour clapped, which was mortifying."),
    ("e043", "2026-05-15", "plain", "Henrik praised the hospital section drawings in the team meeting. I didn't know what to do with my face."),
    ("e044", "2026-05-16", "plain", f"{T3['e044']} Three cups before noon trying to finish the elevations."),
    ("e045", "2026-05-18", "plain", "Ran 6 km after work, first in a while. Everything ached."),
    ("e046", "2026-05-20", "plain", "Packed the kitchen. Found a mug from my first job. Kept it."),
    ("e047", "2026-05-21", "plain", "Practised the Bach again, twenty minutes, then gave up and played something easy."),
    ("e048", "2026-05-22", "plain", "Hospital competition submitted. Went home and slept for ten hours."),
    ("e049", "2026-05-22", "plain", f"{P2['e049']} I'll do it Saturday, I suppose."),
    ("e050", "2026-05-24", "plain", "Did Henrik's revision Saturday morning. It took an hour, which is the annoying part. It could have waited."),
    ("e051", "2026-05-27", "plain", "Last week in the old flat. Strange to see it empty. The light in the evening was always the best thing about it."),
    ("e052", "2026-05-30", "plain", "Moved! Tomek and his flatmate carried everything up three floors and would only accept pizza. The cello made it in one piece."),
    ("e053", "2026-06-01", "plain", "First morning in the new flat. Walked to work in eight minutes. I could get used to this."),
    ("e054", "2026-06-03", "plain", "Unpacked the books. Put the cello in the spare room by the window."),
    ("e055", "2026-06-05", "plain", f"{T7_KEPT['e055']} The film was terrible and we laughed the whole way home."),
    ("e056", "2026-06-06", "plain", "Ran along the new route by the river path, 7 km. Better than the canal."),
    ("e057", "2026-06-08", "plain", "Cello lesson in the new place. Ola came here for once. She liked the room."),
    ("e058", "2026-06-10", "plain", f"{P1['e058']} The client moved the deadline forward by a week."),
    ("e059", "2026-06-11", "plain", "Long day on the hospital drawings. Ate at my desk again."),
    ("e060", "2026-06-12", "plain", "Hospital drawings sent. Henrik said thanks, which he rarely does."),
    ("e061", "2026-06-14", "plain", f"{P3['e061']} He's decided to take the new job."),
    ("e062", "2026-06-15", "plain", "Practised, 30 minutes. The second page of the Bach is starting to make sense."),
    ("e063", "2026-06-16", "plain", "Ines came for dinner at the new flat. We talked about her new office until midnight."),
    ("e064", "2026-06-17", "plain", "Ran 8 km. Hot. Drank a litre of water afterwards."),
    ("e065", "2026-06-18", "markdown", "## Things I like about the new flat\n\n1. the walk to work\n2. the spare room\n3. the plane tree outside the kitchen"),
    ("e066", "2026-06-19", "plain", f"{P2['e066']} Annoyed with myself again."),
    ("e067", "2026-06-20", "plain", "Worked Saturday on the tender drawings. Missed my lesson."),
    ("e068", "2026-06-22", "plain", "Rescheduled the cello lesson. Ola was kind about it."),
    ("e069", "2026-06-23", "plain", "Short walk at lunch with a colleague, Pawel. He's new and asks a lot of good questions."),
    ("e070", "2026-06-24", "plain", f"{T3['e070']} Slept better, though that might be the new flat."),
    ("e071", "2026-06-25", "plain", "Site visit to the library. The brick of the old wing looks beautiful against the glass link. Maybe Henrik was right."),
    ("e072", "2026-06-26", "plain", f"{P1['e072']} The tender went out today."),
    ("e073", "2026-06-27", "plain", "Slept in. Practised for an hour. Felt like myself again."),
    ("e074", "2026-06-28", "plain", "Ran 9 km by the river. Tomek joined for the last two."),
    ("e075", "2026-06-29", "plain", "Ola set a date for the summer lesson break. Six weeks to keep practising on my own."),
    ("e076", "2026-06-30", "plain", "End of June. Four months, a new flat, two competitions. I'd like the summer to be slower."),
    ("u001", None, "plain", f"{T5} Ola says not to worry about it, which makes me worry more."),
    ("u002", None, "plain", "Couldn't sleep, so I sketched the plane tree from memory. Not sure when I'll look at this again."),
]

LONG_ID, LONG_DATE = "e077", "2026-05-01"
LONG = " ".join([
    "A long one, because it has been a long month and I haven't written properly in a while.",
    # work
    "Work first. The hospital competition has taken over the studio. Henrik has us all on it, and the library extension has quietly become something I check on once a week instead of the thing I think about in the shower. I like the hospital brief more than I expected to. There is a courtyard at the centre that everything looks onto, and I've been drawing it over and over, trying to get the light right at different times of day. The structural engineer thinks the cantilever over the entrance is too ambitious. He might be right, but I'm not ready to give it up yet. Pawel, who started last month, has been helping with the models and he is careful in a way I wasn't at his age. I keep meaning to tell him that and I keep not doing it.",
    # the move
    "The move is getting closer and I have that feeling of living in two places at once. Half my books are in boxes, half are still on the shelves, and I keep needing exactly the one I've packed. The new flat has a room I can practise in, and I've already decided where the music stand will go, by the window, facing the plane tree. Tomek says he'll bring his flatmate to help carry things. I'm trying not to think about the three flights of stairs.",
    # the ankle
    f"{T6} I didn't write about it at the time because it seemed so stupid, a grown woman falling off a kerb, but it stopped me running for the best part of two weeks and I missed it more than I thought I would. It's fine now. I've been doing the exercises the physio gave me, the ones with the band, mostly while waiting for the kettle.",
    # cello
    "The cello is the thing that has kept me sane. Even ten minutes in the evening changes the shape of the day. Ola has me working on a Bach movement that is far too hard for me, and I love it and hate it in equal measure. There is a passage near the end of the first page where the notes cross strings so fast I lose my place every time. Ola says to play it at half speed for a week and not to listen to recordings. I listened to three recordings the same evening.",
    # friends
    "Ines is about to start at her new practice and is nervous in a way I haven't seen before. We walked around the park for an hour on Thursday and she talked about whether she'd made a mistake. I don't think she has. I told her so, and then worried that I'd said it too quickly, as if I wasn't listening. I'll ask her again next week, properly.",
    "Tomek seems better. He's still deciding about the job, but he laughs more on the phone. We are closer than we were a year ago and I'm not entirely sure why. Maybe because I call him more.",
    "That's enough for one night. The boards for the hospital are due in three weeks and I want to be asleep before midnight for once.",
])

SESSION_TURNS = [
    ("Counsellor", "How have the last couple of weeks been?"),
    ("Mara", "Busy. The hospital competition, the move, everything at once. I'm sleeping badly."),
    ("Counsellor", "What happens on the nights you sleep badly?"),
    ("Mara", "I lie there going through the drawings in my head. Sometimes I get up and draw."),
    ("Counsellor", "And at work, how are things with Henrik?"),
    ("Mara", "He asks for things late on Fridays and I say yes. Every time."),
    ("Counsellor", T1_COUNSELLOR),
    ("Mara", f"{T1_MARA} I argue with him about designs all the time. It's more that I don't want to be the one who says no to extra work."),
    ("Counsellor", "What would it be like to say no?"),
    ("Mara", "I don't know. I think he'd be disappointed and I'd feel it all weekend."),
    ("Counsellor", "You mentioned feeling it all weekend. What does that feel like?"),
    ("Mara", "Like a weight. I keep checking my phone."),
    ("Counsellor", T11_COUNSELLOR),
    ("Mara", "I don't think it's that bad. I'm tired, but I still like the work."),
    ("Counsellor", "What about when someone is angry with you, at work or anywhere?"),
    ("Mara", P4 + " Even if I think they're wrong, I wait for it to pass."),
    ("Counsellor", "What happens afterwards?"),
    ("Mara", "Usually I go over it later, what I should have said. Sometimes for days."),
    ("Counsellor", "Is there anyone you can talk to when that happens?"),
    ("Mara", "My brother. I call him when I can't sleep. He's good at making me laugh."),
    ("Counsellor", "And the running you mentioned last time?"),
    ("Mara", "It goes first when work gets busy. I know it does and I let it."),
    ("Counsellor", "What do you notice when you haven't run for a while?"),
    ("Mara", "I'm more irritable. I sleep worse."),
    ("Counsellor", "It sounds like the running does something for you."),
    ("Mara", "Maybe. Or maybe I just notice it more when I'm tired anyway."),
    ("Counsellor", "That's fair. What would you like to look at next time?"),
    ("Mara", "The Friday thing, I think. I'd like to try something different with Henrik."),
    ("Counsellor", "Shall we start there next week?"),
    ("Mara", "Yes."),
]

QUESTIONNAIRE = [
    ("What do you do for work?", "I'm an architect at a mid-size studio. Mostly public buildings."),
    ("What helps you calm down when you're stressed?", T8_ANSWER),
    ("How would you describe your sleep?", "Usually fine. Bad when work is busy."),
    ("Who do you turn to when things are hard?", "My brother Tomek, and my friend Ines."),
    ("What do you do for exercise?", "I run, three or four times a week when I can."),
    ("Is there anything you're learning at the moment?", "The cello. I started two years ago."),
]

#: Topics the journal must never touch (T4, T12), checked word by word.
ABSENT = ["mother", "father", "parents", "mum", "dad", "money", "salary", "rent", "savings", "debt",
          "travel", "holiday", "flight", "abroad", "race", "marathon", "half-marathon", "sunday evening"]


def _session() -> str:
    head = ["---", "session: therapy", "started: 2026-05-12T17:00", "language: en", "owner: Mara",
            "therapist: Counsellor", "---", ""]
    body, at = [], 5
    for label, text in SESSION_TURNS:
        mm, ss = divmod(at, 60)
        body.append(f"**[00:{mm:02d}:{ss:02d}] {label}:**\n{text}\n")
        at += 20 + len(text) // 4
    return "\n".join(head) + "\n".join(body)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    entries = [{"id": i, "date": d, "format": f, "text": t} for i, d, f, t in ENTRIES]
    entries.append({"id": LONG_ID, "date": LONG_DATE, "format": "plain", "text": LONG})
    entries.sort(key=lambda e: (e["date"] is None, e["date"] or "", e["id"]))
    by_id = {e["id"]: e["text"] for e in entries}
    session = _session()
    gold = {
        "P1": {"entries": sorted(P1), "sentences": {**P1}},
        "P2": {"entries": sorted(P2), "sentences": P2},
        "P3": {"entries": sorted(P3), "sentences": P3},
        "P4": {"entries": ["session"], "sentences": {"session": P4}},
        "T1": {"entries": ["session"], "sentences": {"session": T1_COUNSELLOR}, "owner_reply": T1_MARA},
        "T2": {"entries": ["e024", "e058"], "absent_phrase": "I gave up running"},
        "T3": {"entries": sorted(T3), "sentences": T3},
        "T4": {"absent": ["parents", "money", "travel"]},
        "T5": {"entries": ["u001"], "sentences": {"u001": T5}},
        "T6": {"entries": [LONG_ID], "sentences": {LONG_ID: T6}},
        "T7": {"entries": ["e028", *sorted(T7_KEPT)], "sentences": {"e028": T7_SELF, **T7_KEPT}},
        "T8": {"entries": ["questionnaire"], "sentences": {"questionnaire": T8_ANSWER}},
        "T9": {"entries": ["e039"], "sentences": {"e039": T9}},
        "T10": {"entries": ["e040"]},
        "T11": {"entries": ["session"], "sentences": {"session": T11_COUNSELLOR}},
        "T12": {"absent": ["race", "Sunday evening"]},
        "move": {"entries": ["e026"], "sentences": {"e026": REASON_MOVE}},
    }
    # Every planted sentence is found in the entry it names.
    for key, item in gold.items():
        for where, sentence in item.get("sentences", {}).items():
            text = session if where == "session" else T8_ANSWER if where == "questionnaire" else by_id[where]
            assert sentence in text, f"{key}: {where} lost its sentence"
    # The absent topics are absent everywhere.
    everything = " ".join([*by_id.values(), session, *(q + " " + a for q, a in QUESTIONNAIRE)]).lower()
    for word in ABSENT:
        assert not re.search(rf"\b{re.escape(word)}\b", everything), f"absent topic present: {word}"
    assert "gave up running" not in everything and "burning out" not in session.split("Mara:**")[-1].lower()
    assert "Bach" in by_id["e039"] and sum("stumbling" in t for t in by_id.values()) == 1
    (OUT / "entries.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries))
    (OUT / "session.md").write_text(session)
    (OUT / "questionnaire.json").write_text(json.dumps(
        [{"question": q, "answer": a} for q, a in QUESTIONNAIRE], indent=1, ensure_ascii=False) + "\n")
    (OUT / "gold.json").write_text(json.dumps(gold, indent=1, ensure_ascii=False) + "\n")
    words = sum(len(t.split()) for t in by_id.values())
    print(f"{len(entries)} entries ({words} words), {len(SESSION_TURNS)} session turns, "
          f"{len(QUESTIONNAIRE)} questionnaire answers; gold checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
