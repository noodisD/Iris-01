"""A blind comparison: the same question to IRIS with and without its history.

    POSTGRES_DB=iris_eval_full   uv run uvicorn iris_api:app --host 127.0.0.1 --port 8010
    POSTGRES_DB=iris_eval_direct uv run uvicorn iris_api:app --host 127.0.0.1 --port 8011
    uv run python scripts/eval_compare.py            # then open http://127.0.0.1:8020

Each question goes to both as a fresh chat. The answers come back as "Answer 1"
and "Answer 2" in random order; the owner picks the better one and only then
sees which was which. Each test chat is deleted from its eval copy afterwards,
so one question never colours the next. Results are kept in
data/eval/results.jsonl, on this laptop.

Each question is two chat turns sent to OpenAI, so nothing is asked until the
owner presses Ask both, with the cost shown beside it.
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg2
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.config import settings
from agent.intelligence import Intelligence

INSTANCES = {
    "with history": ("http://127.0.0.1:8010", "iris_eval_full"),
    "without history": ("http://127.0.0.1:8011", "iris_eval_direct"),
}
RESULTS = Path(settings.DATA_DIR) / "eval" / "results.jsonl"
PAGE = Path(__file__).with_name("eval_compare.html")
REPLY_TOKENS = 400

app = FastAPI()
pending: dict[str, dict] = {}


@app.middleware("http")
async def only_this_page(request: Request, call_next):
    """Asking costs money: only this laptop's own page may ask."""
    host = (request.headers.get("host") or "").split(":")[0]
    origin = request.headers.get("origin")
    if host not in ("127.0.0.1", "localhost") or (
            request.method == "POST" and origin not in (None, "http://127.0.0.1:8020", "http://localhost:8020")):
        return HTMLResponse("Not here.", status_code=403)
    return await call_next(request)


def _records() -> list[dict]:
    if not RESULTS.exists():
        return []
    return [json.loads(line) for line in RESULTS.read_text().splitlines() if line.strip()]


def _forget_chat(dbname: str, session_id: str) -> None:
    """The test chat leaves its eval copy, so the next question starts clean."""
    conn = psycopg2.connect(dbname=dbname, user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
                            host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM conversation_messages WHERE session_id = %s", (session_id,))
        ids = [r[0] for r in cur.fetchall()]
        if ids:
            cur.execute("DELETE FROM embeddings WHERE source_type = 'message' AND source_id = ANY(%s)", (ids,))
            cur.execute("DELETE FROM processing_queue WHERE source_type = 'message' AND source_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM conversation_messages WHERE session_id = %s", (session_id,))
        cur.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))
    conn.close()


async def _ask(client: httpx.AsyncClient, base: str, dbname: str, question: str) -> str:
    opened = (await client.post(f"{base}/api/conversations")).json()["id"]
    parts: list[str] = []
    try:
        async with client.stream("POST", f"{base}/api/conversations/{opened}/messages/stream",
                                 json={"text": question}, timeout=180) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                if "error" in event:
                    raise HTTPException(status_code=502, detail=f"{base}: {event['error']}")
                if event.get("done"):
                    break
                parts.append(event.get("text", ""))
    finally:
        await asyncio.to_thread(_forget_chat, dbname, opened)
    return "".join(parts).strip()


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    return PAGE.read_text()


@app.get("/api/estimate")
async def estimate() -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        bodies = await asyncio.gather(*(client.get(f"{base}/api/voice/estimate") for base, _ in INSTANCES.values()))
    price = Intelligence.PRICE_PER_MTOK.get(settings.OPENAI_MODEL)
    tokens = [b.json()["tokensIn"] for b in bodies]
    if not price:
        return {"text": f"{sum(tokens) // 1000}k tokens in on {settings.OPENAI_MODEL} for both answers"}
    dollars = sum(t * price[0] + REPLY_TOKENS * price[1] for t in tokens) / 1_000_000
    return {"text": f"about ${dollars:.3f} for both answers, on {settings.OPENAI_MODEL}"}


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


@app.post("/api/ask")
async def ask(body: Question) -> dict:
    async with httpx.AsyncClient() as client:
        names = list(INSTANCES)
        answers = await asyncio.gather(*(_ask(client, *INSTANCES[n], body.question) for n in names))
    order = names[:]
    random.shuffle(order)
    qid = uuid.uuid4().hex[:10]
    by_name = dict(zip(names, answers, strict=True))
    pending[qid] = {"question": body.question, "order": order, "answers": by_name}
    return {"id": qid, "answers": [by_name[n] for n in order]}


class Vote(BaseModel):
    id: str
    choice: str = Field(pattern="^(1|2|tie|both_poor)$")
    note: str = Field(default="", max_length=2000)


@app.post("/api/vote")
def vote(body: Vote) -> dict:
    asked = pending.pop(body.id, None)
    if asked is None:
        raise HTTPException(status_code=404, detail="That question is not waiting for a vote.")
    order = asked["order"]
    winner = {"1": order[0], "2": order[1]}.get(body.choice, body.choice)
    record = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "question": asked["question"],
              "answer_1": order[0], "answer_2": order[1], "winner": winner, "note": body.note.strip() or None,
              "answers": asked["answers"]}
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"answer_1": order[0], "answer_2": order[1], "winner": winner, "tally": tally()}


@app.get("/api/tally")
def tally() -> dict:
    counts = {"with history": 0, "without history": 0, "tie": 0, "both_poor": 0}
    for r in _records():
        counts[r["winner"]] = counts.get(r["winner"], 0) + 1
    return counts


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8020)
