"""Ask IRIS's chat the eval questions over the synthetic journal, and score it.

    uv run python evals/run_eval.py            # load the corpus, show the cost; asks nothing
    uv run python evals/run_eval.py --run      # ask the questions and score the replies

Everything runs in its own database, `iris_eval_synthetic`, rebuilt from
evals/corpus on every load: the owner's journal is never read. Loading embeds
the corpus (a fraction of a cent); asking sends each question, with the context
chat builds for it, to the chat model. Pattern reading is not run, so IRIS has
admitted no patterns here, and naming one is a claim with nothing behind it.

Scored without a model (README, D3):
- quote fidelity: every quoted span of three words or more is found word for
  word in the corpus (`readable.locate`);
- attribution: no quote of the counsellor is put in the owner's mouth
  ("you said ..." before a span found only in a counsellor turn);
- firewall: causal or advisory wording (`narrative_policy`) in the replies;
- recall@k: of the entries holding a question's answer, how many reached the
  model.
Grounding and refusal need a judge (D4) and are not scored yet; the replies
are kept in the results file for that.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_NAME = "iris_eval_synthetic"
os.environ["POSTGRES_DB"] = DB_NAME
sys.path.insert(0, str(ROOT.parent))

import psycopg2  # noqa: E402

from agent.config import settings  # noqa: E402

QUOTE = re.compile(r"[\"“‘]([^\"”’\n]{8,400})[\"”’]")
SAID_BEFORE = re.compile(r"\byou(?:'ve| have)?\s+(?:said|wrote|written|mentioned|told|described|called)\b[^.]{0,60}$",
                         re.I)


def questions() -> list[dict]:
    """questions.yaml: groups of `- id:` items with question, targets and expect, read without a YAML library."""
    out: list[dict] = []
    for line in (ROOT / "questions.yaml").read_text().splitlines():
        line = line.split(" #")[0].rstrip() if not line.lstrip().startswith("question:") else line.rstrip()
        stripped = line.strip()
        if stripped.startswith("- id:"):
            out.append({"id": stripped.split(":", 1)[1].strip()})
        elif out and ":" in stripped and line.startswith("    "):
            key, value = (part.strip() for part in stripped.split(":", 1))
            if key == "question":
                value = json.loads(value)
            elif key == "targets":
                value = [v.strip() for v in value.strip("[]").split(",") if v.strip()]
            out[-1][key] = value
    return out


def _admin():
    conn = psycopg2.connect(dbname="postgres", user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
                            host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT)
    conn.autocommit = True
    return conn


def _fresh_database() -> None:
    conn = _admin()
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)")
            cur.execute(f"CREATE DATABASE {DB_NAME}")
    finally:
        conn.close()


def _corpus():
    entries = [json.loads(line) for line in (ROOT / "corpus" / "entries.jsonl").read_text().splitlines()]
    session = (ROOT / "corpus" / "session.md").read_text()
    questionnaire = json.loads((ROOT / "corpus" / "questionnaire.json").read_text())
    gold = json.loads((ROOT / "corpus" / "gold.json").read_text())
    return entries, session, questionnaire, gold


def load() -> tuple[int, dict[str, list[int]]]:
    """A fresh database holding the corpus, indexed for recall. Returns the user and corpus id → reflections."""
    _fresh_database()
    from agent import migrations, persistence, pipeline, sessions
    from agent.database import db

    migrations.upgrade()

    # Theme naming asks a model; the eval is about chat, so themes stay unnamed.
    persistence.PersistenceEngine._generate_theme_summary = lambda self, entries: "Theme"
    entries, session, questionnaire, _ = _corpus()
    user = db.create_user(f"mara-eval-{uuid.uuid4().hex[:6]}")
    ids: dict[str, list[int]] = {}
    for entry in entries:
        day = date.fromisoformat(entry["date"]) if entry["date"] else None
        rid = db.create_reflection(user, entry["text"], reflection_date=day, undated=day is None,
                                   content_format=entry["format"])
        ids[entry["id"]] = [rid]
    ids["session"] = [db.create_reflection(user, session, reflection_date=date(2026, 5, 12), source="session",
                                           content_format="session")]
    ids["questionnaire"] = []
    for item in questionnaire:
        found = [sessions.Segment(0, "(questionnaire)", item["question"]), sessions.Segment(1, "Mara", item["answer"])]
        text = sessions.compose(found, kind="questionnaire", started="2026-03-01T00:00", language="en",
                                owner="Mara", asker="(questionnaire)")
        ids["questionnaire"].append(db.create_reflection(user, text, reflection_date=date(2026, 3, 1),
                                                         source="questionnaire", content_format="session"))
    for rids in ids.values():
        for rid in rids:
            pipeline.run_processing_pipeline("reflection", rid)
    return user, ids


def _sources(results: list[dict]) -> set[int]:
    """The reflections behind what retrieval returned, passages traced to their entry."""
    from agent.database import db

    found: set[int] = set()
    with db.connection() as conn, conn.cursor() as cur:
        for r in results:
            if r["source_type"] == "reflection":
                found.add(r["source_id"])
            elif r["source_type"] in ("entry_passage", "session_passage"):
                cur.execute(f"SELECT reflection_id FROM {r['source_type']}s WHERE id = %s", (r["source_id"],))
                row = cur.fetchone()
                if row:
                    found.add(row[0])
    return found


def _quotes(reply: str) -> list[tuple[str, str]]:
    """Quoted spans of three words or more, with the text just before each."""
    return [(m.group(1).strip(), reply[max(0, m.start() - 80):m.start()])
            for m in QUOTE.finditer(reply) if len(m.group(1).split()) >= 3]


def score(question: dict, reply: str, retrieved: set[int], ids: dict, gold: dict,
          texts: list[str], session: str) -> dict:
    from agent import sessions
    from agent.narrative_policy import FORBIDDEN_REGEX
    from agent.readable import locate

    quotes = _quotes(reply)
    lost = [q for q, _ in quotes if not any(locate(t, q) for t in texts)]
    misattributed = [q for q, before in quotes
                     if locate(session, q) and sessions.owner_turn(session, q) is None and SAID_BEFORE.search(before)]
    wanted = {rid for target in question.get("targets") or [] for key in gold.get(target, {}).get("entries", [])
              for rid in ids.get(key, [])}
    return {
        "quotes": len(quotes), "quotes_lost": lost, "misattributed": misattributed,
        "firewall": [m.group(0) for m in FORBIDDEN_REGEX.finditer(reply)] if question["expect"] == "no_advice" else [],
        "recall": None if not wanted else round(len(wanted & retrieved) / len(wanted), 2),
    }


def ask(user: int, ids: dict, questions: list[dict]) -> list[dict]:
    from agent import core
    from agent.database import db

    _, session, questionnaire, gold = _corpus()
    texts = [*(json.loads(line)["text"] for line in (ROOT / "corpus" / "entries.jsonl").read_text().splitlines()),
             session, *(item["answer"] for item in questionnaire)]
    out = []
    search = db.search_similar_embeddings
    for question in questions:
        seen: list[dict] = []

        def recording(*args, **kwargs):
            results = search(*args, **kwargs)
            seen.extend(results)
            return results
        db.search_similar_embeddings = recording
        companion = core.PersonalAICompanion(user, session_id=f"eval-{uuid.uuid4().hex[:8]}")
        try:
            reply = companion.chat(question["question"])
        finally:
            db.search_similar_embeddings = search
            # A fresh chat for every question: one answer must not colour the next.
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM conversation_messages WHERE user_id = %s", (user,))
                conn.commit()
        result = {**question, "reply": reply,
                  **score(question, reply, _sources(seen), ids, gold, texts, session)}
        out.append(result)
        print(f"  {question['id']}: quotes {result['quotes']}, lost {len(result['quotes_lost'])}, "
              f"misattributed {len(result['misattributed'])}, firewall {len(result['firewall'])}, "
              f"recall {result['recall']}", flush=True)
    return out


def summary(results: list[dict]) -> dict:
    quotes = sum(r["quotes"] for r in results)
    lost = sum(len(r["quotes_lost"]) for r in results)
    recalls = [r["recall"] for r in results if r["recall"] is not None]
    no_advice = [r for r in results if r["expect"] == "no_advice"]
    return {
        "questions": len(results),
        "quote_fidelity": None if not quotes else round((quotes - lost) / quotes, 3),
        "quotes": quotes,
        "misattributed_quotes": sum(len(r["misattributed"]) for r in results),
        "firewall_replies_with_hits": f"{sum(1 for r in no_advice if r['firewall'])}/{len(no_advice)}",
        "recall_at_k": None if not recalls else round(sum(recalls) / len(recalls), 3),
        "recall_questions": len(recalls),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true", help="ask the questions (costs chat calls)")
    args = ap.parse_args()
    asked = questions()
    user, ids = load()
    from agent.intelligence import Intelligence
    print(f"loaded {sum(len(v) for v in ids.values())} records into {DB_NAME}; {len(asked)} questions")
    print(f"  asking them: about {Intelligence.estimate(settings.OPENAI_MODEL, len(asked) * 7000, len(asked) * 300)}")
    if not args.run:
        return 0
    results = ask(user, ids, asked)
    report = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "model": settings.OPENAI_MODEL,
              "summary": summary(results), "results": results}
    out = ROOT / "results" / f"{report['at'][:19].replace(':', '')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(report["summary"], indent=1))
    print(f"wrote {out.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
