"""
IRIS Multi-User API
This is the HTTP layer that wraps your CLI companion logic.
It handles authentication, routing requests to the right companion instance, and returning responses.
"""

import logging

from agent.logging_config import configure_logging

# Configure logging first, before any other imports
configure_logging()
logger = logging.getLogger(__name__)

import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

# Load environment variables
load_dotenv()

# Import the companion system
try:
    from agent.core import PersonalAICompanion
    from agent.database import db
    from agent.insights_service import InsightsService
    from agent.trackers.habits import HabitTracker
    from agent.trackers.reflections import ReflectionService

    COMPANION_AVAILABLE = True
    logger.info("PersonalAICompanion and db imported successfully")
except ImportError as e:
    COMPANION_AVAILABLE = False
    logger.error(f"ImportError: Could not import core components: {e}")
except Exception as e:
    COMPANION_AVAILABLE = False
    logger.error(f"Error importing PersonalAICompanion: {e}")

# Built single-page app (Vite output), served by this same process in production.
# In dev the Vite server on :5173 proxies /api here instead, so this stays unused.
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler for app startup/shutdown"""
    if COMPANION_AVAILABLE:
        logger.info("Initializing database schema...")
        try:
            db.create_schema()
            logger.info("Database schema initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
    yield

# Initialize FastAPI app
app = FastAPI(title="IRIS Companion API", version="0.1.0", lifespan=lifespan)

# ============================================================================
# DATA MODELS
# ============================================================================


# ============================================================================
# HABIT MODELS
# ============================================================================

class HabitCreate(BaseModel):
    """Create a new habit"""
    name: str
    description: str | None = None
    frequency_type: str = "daily"  # daily, weekly, specific_days
    habit_type: str = "completion"  # completion, duration, count
    weekly_target: float = 0
    tracking_metric: str | None = "completion"
    category: str | None = "general"

class HabitUpdate(BaseModel):
    """Update habit fields"""
    name: str | None = None
    description: str | None = None
    habit_type: str | None = None
    weekly_target: float | None = None
    tracking_metric: str | None = None
    is_active: bool | None = None

class HabitCompletion(BaseModel):
    """Log a habit completion"""
    habit_id: int
    value: float = 1.0
    date: str | None = None  # ISO date string, defaults to today
    notes: str | None = None

class HabitSkip(BaseModel):
    """Log a habit skip"""
    habit_id: int
    date: str | None = None  # ISO date string, defaults to today
    reason: str | None = None

class HabitResponse(BaseModel):
    """Habit response model"""
    id: int
    name: str
    description: str | None
    frequency_type: str
    category: str
    is_active: bool
    current_streak: int
    longest_streak: int
    total_completions: int
    created_at: str


# ============================================================================
# REFLECTION MODELS
# ============================================================================

class ReflectionCreate(BaseModel):
    """Create a new reflection"""
    content: str
    energy_level: int | None = None  # 1-10
    clarity_level: int | None = None # 1-10
    tags: list[str] | None = None
    reflection_date: str | None = None  # ISO date string

class ReflectionUpdate(BaseModel):
    """Update reflection fields"""
    content: str | None = None
    energy_level: int | None = None
    clarity_level: int | None = None
    tags: list[str] | None = None

class ReflectionResponse(BaseModel):
    """Reflection response model"""
    id: int
    reflection_date: str
    content: str
    mood: str | None
    energy_level: int | None
    clarity_level: int | None
    tags: list[str] | None
    created_at: str
    updated_at: str


# ============================================================================
# SINGLE-USER SEAM
# ============================================================================
# IRIS runs as a personal, single-user local app: one process, one database,
# bound to loopback. There is no login and no token — every route resolves (or
# lazily creates on first run) the one local user through get_current_user_id.
# Tests override this dependency via app.dependency_overrides.

DEFAULT_USERNAME = os.getenv("IRIS_DEFAULT_USER", "local")
DEFAULT_PASSWORD = os.getenv("IRIS_DEFAULT_PASSWORD", "local")


def get_current_user_id() -> int:
    """Resolve the single local user's id, creating the user on first run."""
    user = db.get_user(DEFAULT_USERNAME)
    if user:
        return user["id"]
    return db.create_user(DEFAULT_USERNAME, DEFAULT_PASSWORD)


# ============================================================================
# ROOT & STATIC ENDPOINTS
# ============================================================================

# Mount the built SPA's static assets (Vite emits /assets/*).
if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

@app.get("/")
async def root():
    """Serve the built SPA. Run `npm run build` in frontend/ if this 404s."""
    spa_index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(spa_index):
        return FileResponse(spa_index)
    return {"message": "IRIS API online. SPA not built — run `npm run build` in frontend/."}

# Health check
@app.get("/health")
async def health_check():
    """Liveness *and* readiness: an API that cannot reach PostgreSQL is not
    healthy, and reporting ok regardless meant every data route returned 500
    while monitoring saw a green service."""
    checks = {"database": "down"}
    try:
        await run_in_threadpool(db.ping)
        checks["database"] = "ok"
    except Exception as e:
        logger.error(f"Health check: database unreachable: {e}")

    healthy = checks["database"] == "ok"
    return Response(
        content=json.dumps({
            "status": "ok" if healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.now(UTC).isoformat(),
        }),
        media_type="application/json",
        status_code=200 if healthy else 503,
    )


# ============================================================================
# CHAT ENDPOINTS
# ============================================================================


@app.post("/api/chat/greeting")
async def get_greeting(user_id: int = Depends(get_current_user_id)):
    """Get a dynamic greeting for the user."""
    try:
        companion = PersonalAICompanion(user_id=user_id)
        greeting = await run_in_threadpool(companion.generate_initial_greeting)
        return {"greeting": greeting}
    except Exception as e:
        logger.error(f"Greeting error: {e}")
        return {"greeting": "Hi, I'm Iris. How are you today?"}


@app.post("/api/chat/proactive")
async def proactive_chat(request: dict, user_id: int = Depends(get_current_user_id)):
    """Trigger a proactive comment from IRIS."""
    action_type = request.get("action_type")
    details = request.get("details", {})

    if not action_type:
        raise HTTPException(status_code=400, detail="action_type required")

    try:
        companion = PersonalAICompanion(user_id=user_id)
        iris_response = await run_in_threadpool(
            companion.generate_proactive_comment, action_type, details
        )
        # Response already persisted by companion.generate_proactive_comment() -> memory.add_message()
        return {"message": iris_response}
    except Exception as e:
        logger.error(f"Proactive error: {e}")
        return {"message": "..."} # Fail silently


# ============================================================================
# CONVERSATION ENDPOINTS (single-user; used by the integrated frontend)
# ============================================================================


def _conversation_id_for(user_id: int) -> str:
    return f"conv_{user_id}"


def _iso(ts) -> str:
    return ts.isoformat() if hasattr(ts, "isoformat") else str(ts)


@app.get("/api/conversations/current")
async def get_current_conversation(user_id: int = Depends(get_current_user_id)):
    """Return the user's single rolling conversation (Conversation contract shape)."""
    history = db.get_chat_history(user_id, limit=200)
    now_iso = datetime.now(UTC).isoformat()
    return {
        "id": _conversation_id_for(user_id),
        "userId": str(user_id),
        "startedAt": _iso(history[0]["created_at"]) if history else now_iso,
        "lastMessageAt": _iso(history[-1]["created_at"]) if history else now_iso,
        "messageCount": len(history),
        "inferred": [],
    }


@app.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str, user_id: int = Depends(get_current_user_id)):
    """Return the conversation's messages as ChatMessage[] (role assistant→iris)."""
    history = db.get_chat_history(user_id, limit=200)
    return [
        {
            "id": f"{conversation_id}_{i}",
            "conversationId": conversation_id,
            "role": "iris" if m["role"] == "assistant" else m["role"],
            "text": m["content"],
            "createdAt": _iso(m["created_at"]),
        }
        for i, m in enumerate(history)
    ]


@app.get("/api/conversations/{conversation_id}/inferred")
async def get_conversation_inferred(conversation_id: str, user_id: int = Depends(get_current_user_id)):
    """Inferred tags for the chat rail. Stubbed empty until wired to insights."""
    return []


@app.post("/api/conversations/{conversation_id}/messages/stream")
async def stream_conversation_reply(
    conversation_id: str,
    request: dict,
    user_id: int = Depends(get_current_user_id),
):
    """
    Stream IRIS's reply as Server-Sent Events.

    companion.chat() is synchronous: it persists both the user message and the
    reply, then returns the whole reply string. We run it off the event loop and
    chunk the result word-by-word so the frontend renders it progressively.
    Emits `data: {"text": "..."}` chunks then a final `data: {"done": true, ...}`.
    """
    text = (request or {}).get("text", "")

    async def event_gen():
        if not COMPANION_AVAILABLE:
            yield f"data: {json.dumps({'text': 'Companion system not available.'})}\n\n"
            yield f"data: {json.dumps({'done': True, 'messageId': 'unavailable'})}\n\n"
            return
        try:
            companion = PersonalAICompanion(user_id=user_id)
            reply = await run_in_threadpool(companion.chat, text)
        except Exception as e:
            logger.error(f"Error streaming chat reply: {e}")
            reply = f"I encountered an error processing your message: {e}"

        for idx, word in enumerate(reply.split(" ") if reply else []):
            chunk = word if idx == 0 else " " + word
            yield f"data: {json.dumps({'text': chunk})}\n\n"

        message_id = f"{conversation_id}_{int(datetime.now(UTC).timestamp() * 1000)}"
        yield f"data: {json.dumps({'done': True, 'messageId': message_id})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ============================================================================
# HABIT ENDPOINTS
# ============================================================================

class AppHabitCreate(BaseModel):
    """Habit create payload from the integrated frontend (Pick<Habit,'name'|'tag'|'intent'|'color'>)."""
    name: str
    tag: str | None = None
    intent: str | None = None
    color: str | None = None


class HabitToggle(BaseModel):
    """Toggle a habit's completion for a date (defaults to today)."""
    done: bool
    date: str | None = None  # ISO date string


# Stable theme colors assigned deterministically when a habit has none stored.
HABIT_COLORS = ["sage", "amber", "indigo", "rose"]


def _habit_to_contract(habit: dict, user_id: int, window_days: int = 60) -> dict:
    """Map a habit DB row → the frontend `Habit` shape, incl. recentDays history."""
    hid = habit["id"]
    today = date.today()
    start = today - timedelta(days=window_days - 1)
    by_date = {c["completion_date"]: c for c in db.get_habit_completions(hid, start, today)}
    recent_days = []
    for i in range(window_days):
        c = by_date.get(start + timedelta(days=i))
        recent_days.append(1 if (c and c["is_completed"]) else 0)
    done_today = bool(by_date.get(today) and by_date[today]["is_completed"])
    return {
        "id": str(hid),
        "userId": str(user_id),
        "name": habit["name"],
        "tag": habit.get("category") or habit.get("frequency_type") or "daily",
        "intent": habit.get("description"),
        "color": habit.get("color") or HABIT_COLORS[hid % len(HABIT_COLORS)],
        "supports": [],
        "streakDays": habit.get("current_streak") or 0,
        "bestStreak": habit.get("longest_streak") or 0,
        "doneToday": done_today,
        "recentDays": recent_days,
    }


@app.get("/api/habits")
async def list_habits(user_id: int = Depends(get_current_user_id)):
    """List all active habits (raw tracker shape; /api/habits/today is the UI contract)."""
    tracker = HabitTracker(user_id)
    habits = tracker.get_habits(active_only=True)
    return {"habits": habits}

@app.post("/api/habits")
async def create_habit_app(habit: AppHabitCreate, user_id: int = Depends(get_current_user_id)):
    """Create a habit and return it in the frontend `Habit` contract shape."""
    tracker = HabitTracker(user_id)
    habit_id = tracker.create_habit(
        name=habit.name,
        description=habit.intent,
        category=habit.tag or "general",
    )
    contract = _habit_to_contract(tracker.get_habit(habit_id), user_id)
    if habit.color:
        contract["color"] = habit.color
    return contract

@app.get("/api/habits/today")
async def get_today_habits(user_id: int = Depends(get_current_user_id)):
    """Today's habits + aggregates as the frontend `HabitsTodayResponse` shape."""
    tracker = HabitTracker(user_id)
    habits = [_habit_to_contract(h, user_id) for h in tracker.get_habits(active_only=True)]
    rates = [sum(h["recentDays"][-30:]) / 30 for h in habits]
    return {
        "habits": habits,
        "doneCount": sum(1 for h in habits if h["doneToday"]),
        "totalCount": len(habits),
        "consistency30d": round(sum(rates) / len(rates), 3) if rates else 0.0,
        "longestActiveStreak": max((h["streakDays"] for h in habits), default=0),
    }

@app.post("/api/habits/{habit_id}/toggle")
async def toggle_habit(habit_id: int, toggle: HabitToggle, user_id: int = Depends(get_current_user_id)):
    """Mark a habit done/undone for a date and return the updated `Habit`."""
    tracker = HabitTracker(user_id)
    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")
    toggle_date = None
    if toggle.date:
        try:
            toggle_date = datetime.fromisoformat(toggle.date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")
    if toggle.done:
        tracker.log_completion(habit_id, toggle_date)
    else:
        db.uncomplete_habit(habit_id, toggle_date)
    tracker.update_streaks(habit_id)
    return _habit_to_contract(tracker.get_habit(habit_id), user_id)

@app.get("/api/habits/weekly")
async def get_weekly_summary(user_id: int = Depends(get_current_user_id)):
    """Get weekly habit summary"""
    tracker = HabitTracker(user_id)
    summary = tracker.get_weekly_summary()
    return summary

@app.get("/api/habits/consistency/{days}")
async def get_consistency_report(days: int = 30, user_id: int = Depends(get_current_user_id)):
    """Get consistency report across all habits"""

    tracker = HabitTracker(user_id)
    report = tracker.get_consistency_report(days)
    return report

@app.get("/api/habits/{habit_id}")
async def get_habit(habit_id: int, user_id: int = Depends(get_current_user_id)):
    """Get details of a specific habit"""
    tracker = HabitTracker(user_id)
    habit = tracker.get_habit(habit_id)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return habit

@app.put("/api/habits/{habit_id}")
async def update_habit(habit_id: int, updates: HabitUpdate, user_id: int = Depends(get_current_user_id)):
    """Update a habit's properties"""
    tracker = HabitTracker(user_id)
    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    update_dict = updates.dict(exclude_none=True)
    tracker.update_habit(habit_id, **update_dict)
    return {"message": "Habit updated successfully"}

@app.delete("/api/habits/{habit_id}")
async def delete_habit(habit_id: int, user_id: int = Depends(get_current_user_id)):
    """Delete a habit (soft-delete)"""
    tracker = HabitTracker(user_id)
    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    tracker.delete_habit(habit_id)
    return {"message": "Habit deleted successfully"}

@app.post("/api/habits/complete")
async def log_completion(completion: HabitCompletion, user_id: int = Depends(get_current_user_id)):
    """Log a habit completion"""
    tracker = HabitTracker(user_id)

    if not tracker.get_habit(completion.habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    # Parse date if provided
    completion_date = None
    if completion.date:
        try:
            completion_date = datetime.fromisoformat(completion.date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")

    tracker.log_completion(completion.habit_id, completion_date, completion.value, completion.notes)
    streak_info = tracker.update_streaks(completion.habit_id)

    return {
        "message": "Completion logged successfully",
        "streaks": streak_info
    }

@app.post("/api/habits/skip")
async def log_skip(skip: HabitSkip, user_id: int = Depends(get_current_user_id)):
    """Log a habit skip"""
    tracker = HabitTracker(user_id)

    if not tracker.get_habit(skip.habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    # Parse date if provided
    skip_date = None
    if skip.date:
        try:
            skip_date = datetime.fromisoformat(skip.date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")

    tracker.log_skip(skip.habit_id, skip_date, skip.reason)
    return {"message": "Skip logged successfully"}

@app.get("/api/habits/{habit_id}/calendar")
async def get_habit_calendar(habit_id: int, start: str, end: str, user_id: int = Depends(get_current_user_id)):
    """Get a calendar view of habit completions in a date range"""
    tracker = HabitTracker(user_id)

    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    # Parse dates
    try:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")

    calendar = tracker.get_calendar(habit_id, start_date, end_date)
    return {"calendar": calendar, "habit_id": habit_id}


# ============================================================================
# REFLECTION ENDPOINTS
# ============================================================================

@app.get("/api/reflections")
async def list_reflections(user_id: int = Depends(get_current_user_id), limit: int = 30):
    """List recent reflections"""
    service = ReflectionService(user_id)
    reflections = service.get_reflections(limit=limit)
    return {"reflections": reflections}

@app.post("/api/reflections")
async def create_reflection(reflection: ReflectionCreate, user_id: int = Depends(get_current_user_id)):
    """Create a new reflection"""
    service = ReflectionService(user_id)

    # Parse date if provided
    reflection_date = None
    if reflection.reflection_date:
        try:
            reflection_date = datetime.fromisoformat(reflection.reflection_date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")

    try:
        reflection_id = service.create_reflection(
            content=reflection.content,
            reflection_date=reflection_date,
            energy_level=reflection.energy_level,
            clarity_level=reflection.clarity_level,
            tags=reflection.tags
        )
        # No background task here: ReflectionService.create_reflection already
        # runs the pipeline. Scheduling it again embedded every reflection twice,
        # paying OpenAI twice and re-entering the window that made concurrent
        # ingests mis-attribute each other's content.
        return {"reflection_id": reflection_id, "message": "Reflection saved successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/reflections/moods")
async def get_mood_trend(user_id: int = Depends(get_current_user_id), days: int = 30):
    """Get mood trend data"""
    service = ReflectionService(user_id)
    trend = service.get_mood_trend(days)
    return trend

@app.get("/api/reflections/summary")
async def get_reflection_summary(user_id: int = Depends(get_current_user_id), days: int = 30):
    """Get comprehensive reflection summary"""
    service = ReflectionService(user_id)
    summary = service.get_reflection_summary(days)
    return summary

@app.get("/api/reflections/tags")
async def get_tags_summary(user_id: int = Depends(get_current_user_id), days: int = 30):
    """Get tags summary from reflections"""
    service = ReflectionService(user_id)
    tags = service.get_tag_summary(days)
    return tags

@app.get("/api/reflections/{reflection_id}")
async def get_reflection(reflection_id: int, user_id: int = Depends(get_current_user_id)):
    """Get a specific reflection"""
    service = ReflectionService(user_id)
    reflection = service.get_reflection(reflection_id)

    if not reflection:
        raise HTTPException(status_code=404, detail="Reflection not found")

    return reflection

@app.put("/api/reflections/{reflection_id}")
async def update_reflection(reflection_id: int, updates: ReflectionUpdate, user_id: int = Depends(get_current_user_id)):
    """Update a reflection"""
    service = ReflectionService(user_id)

    if not service.get_reflection(reflection_id):
        raise HTTPException(status_code=404, detail="Reflection not found")

    try:
        update_dict = updates.dict(exclude_none=True)
        service.update_reflection(reflection_id, **update_dict)
        return {"message": "Reflection updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/reflections/{reflection_id}")
async def delete_reflection(reflection_id: int, user_id: int = Depends(get_current_user_id)):
    """Delete a reflection"""
    service = ReflectionService(user_id)

    if not service.get_reflection(reflection_id):
        raise HTTPException(status_code=404, detail="Reflection not found")

    service.delete_reflection(reflection_id)
    return {"message": "Reflection deleted successfully"}


# ============================================================================
# JOURNAL ENDPOINTS (single-user; frontend JournalEntry mapped onto reflections)
# ============================================================================

class JournalCreate(BaseModel):
    """Journal create payload from the frontend (Pick<JournalEntry,'lines'|'mood'>)."""
    lines: list[str]
    mood: int | None = None  # 1-10, stored as the reflection's energy_level


def _reflection_to_journal(r: dict, user_id: int) -> dict:
    """Map a reflection row → the frontend `JournalEntry` shape."""
    content = r.get("content") or ""
    created = r.get("created_at") or r.get("reflection_date")
    return {
        "id": str(r["id"]),
        "userId": str(user_id),
        "lines": content.split("\n"),
        "mood": r.get("energy_level"),
        "tags": r.get("tags") or [],
        "createdAt": _iso(created),
    }


@app.get("/api/journal")
async def list_journal(user_id: int = Depends(get_current_user_id),
                       limit: int = 50, cursor: str | None = None):
    """Return reflections as the frontend `JournalListResponse` (newest first).

    `cursor` is the id of the last entry of the previous page; `nextCursor` is
    returned only when another page exists. The frontend has always sent this
    parameter — it was previously ignored, so paging silently returned page one
    forever.
    """
    before_id = None
    if cursor:
        try:
            before_id = int(cursor)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    service = ReflectionService(user_id)
    # Fetch one extra row to learn whether a further page exists.
    rows = service.get_reflections(limit=limit + 1, before_id=before_id)
    has_more = len(rows) > limit
    rows = rows[:limit]

    body = {
        "entries": [_reflection_to_journal(r, user_id) for r in rows],
        "recurringPhrases": [],
    }
    if has_more and rows:
        body["nextCursor"] = str(rows[-1]["id"])
    return body


@app.post("/api/journal")
async def create_journal_entry(entry: JournalCreate, user_id: int = Depends(get_current_user_id)):
    """Create a reflection from journal lines/mood and return the `JournalEntry`."""
    service = ReflectionService(user_id)
    content = "\n".join(entry.lines).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Journal entry cannot be empty")
    try:
        reflection_id = service.create_reflection(
            content=content,
            energy_level=entry.mood,
            tags=[],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _reflection_to_journal(service.get_reflection(reflection_id), user_id)


# ============================================================================
# SETTINGS ENDPOINTS (single-user; User/UserPreferences, knowledge, connectors)
# ============================================================================

# Incoming PATCH /user/preferences keys (frontend camelCase) → app_settings columns.
_PREF_KEY_MAP = {
    "tone": "tone",
    "density": "density",
    "dailyCheckinTime": "daily_checkin_time",
    "weeklyReviewTime": "weekly_review_time",
    "maxNudgesPerDay": "max_nudges_per_day",
    "threadsListenedFor": "threads",
}

# Static connector catalog. There is no real OAuth/data-source backend yet, so
# every connector defaults to 'off'; the user's toggles persist in app_settings.
CONNECTORS_CATALOG = [
    {"id": "fitbit-air", "name": "Fitbit Air", "scopeDescription": "Sleep, HRV, resting heart rate", "featured": True},
    {"id": "google-health", "name": "Google Health Connect", "scopeDescription": "Steps, workouts, sleep"},
    {"id": "apple-health", "name": "Apple Health", "scopeDescription": "Activity, sleep, vitals"},
    {"id": "calendar", "name": "Calendar", "scopeDescription": "Event titles and timing"},
    {"id": "spotify", "name": "Spotify", "scopeDescription": "Listening history and mood signals"},
    {"id": "photos", "name": "Photos", "scopeDescription": "Metadata only — places and times"},
    {"id": "messages", "name": "Messages", "scopeDescription": "On-device sentiment, never content"},
    {"id": "location", "name": "Location", "scopeDescription": "Coarse place patterns"},
]
_CONNECTOR_IDS = {c["id"] for c in CONNECTORS_CATALOG}
_CONNECTOR_ACTION_STATE = {"connect": "connected", "pause": "paused", "disconnect": "off"}


def _age_days(ts) -> int:
    """Whole days between a timestamp (datetime or ISO string) and now."""
    if not ts:
        return 0
    try:
        dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return 0
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return max(0, (datetime.now() - dt).days)


def _user_to_contract(user_id: int) -> dict:
    """Build the frontend `User` shape from users + user_app_settings."""
    s = db.get_app_settings(user_id) or {}
    created = s.get("created_at")
    return {
        "id": str(user_id),
        "name": s.get("name") or "",
        "createdAt": _iso(created) if created else _iso(datetime.now(UTC)),
        "dayInJourney": _age_days(created) if created else 0,
        "timezone": s.get("timezone") or "UTC",
        "preferences": {
            "tone": s.get("tone") or "warm",
            "density": s.get("density") or "balanced",
            "dailyCheckinTime": s.get("daily_checkin_time"),
            "weeklyReviewTime": s.get("weekly_review_time"),
            "maxNudgesPerDay": s.get("max_nudges_per_day") if s.get("max_nudges_per_day") is not None else 3,
            "threadsListenedFor": s.get("threads") or [],
        },
    }


def _connectors_for(user_id: int) -> list:
    """Static connector catalog with each state overlaid from app_settings."""
    s = db.get_app_settings(user_id) or {}
    states = s.get("connectors") or {}
    out = []
    for c in CONNECTORS_CATALOG:
        item = dict(c)
        item["state"] = states.get(c["id"], "off")
        out.append(item)
    return out


@app.get("/api/user")
async def get_app_user(user_id: int = Depends(get_current_user_id)):
    """Return the frontend `User` (profile + app preferences)."""
    return _user_to_contract(user_id)


@app.patch("/api/user/preferences")
async def update_app_preferences(prefs: dict, user_id: int = Depends(get_current_user_id)):
    """Merge a Partial<UserPreferences> into the app-settings store; return `User`."""
    fields = {_PREF_KEY_MAP[k]: v for k, v in prefs.items() if k in _PREF_KEY_MAP}
    if fields:
        db.upsert_app_settings(user_id, **fields)
    return _user_to_contract(user_id)


@app.get("/api/knowledge")
async def list_knowledge(user_id: int = Depends(get_current_user_id)):
    """Return the user's themes as the frontend `KnownFact[]`."""
    return [
        {
            "id": str(t["id"]),
            "fact": t["summary"],
            "source": "pattern",
            "ageDays": _age_days(t.get("first_seen_at")),
            "editable": True,
        }
        for t in db.get_themes(user_id)
    ]


@app.delete("/api/knowledge/{fact_id}")
async def forget_knowledge(fact_id: int, user_id: int = Depends(get_current_user_id)):
    """Forget a fact (delete the underlying theme), guarding ownership."""
    theme = db.get_theme_by_id(fact_id)
    if not theme or theme.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Fact not found")
    db.delete_theme(fact_id)
    return {"ok": True}


@app.get("/api/connectors")
async def list_connectors(user_id: int = Depends(get_current_user_id)):
    """Return the static connector catalog with persisted per-user states."""
    return _connectors_for(user_id)


@app.post("/api/connectors/{connector_id}/{action}")
async def set_connector_state(connector_id: str, action: str, user_id: int = Depends(get_current_user_id)):
    """Toggle a connector's state (connect|pause|disconnect) and persist it."""
    if connector_id not in _CONNECTOR_IDS:
        raise HTTPException(status_code=404, detail="Connector not found")
    if action not in _CONNECTOR_ACTION_STATE:
        raise HTTPException(status_code=400, detail="Invalid action")
    s = db.get_app_settings(user_id) or {}
    states = dict(s.get("connectors") or {})
    states[connector_id] = _CONNECTOR_ACTION_STATE[action]
    db.upsert_app_settings(user_id, connectors=states)
    return next(c for c in _connectors_for(user_id) if c["id"] == connector_id)


# ============================================================================
# ONBOARDING ENDPOINTS (single-user; configures the local user)
# ============================================================================

# Ordered first-run steps with the answer key each one collects. The current
# step is the first whose answer is still missing (or 'done' once complete).
_ONBOARDING_STEPS = [
    ("name", "name"),
    ("reason", "reason"),
    ("threads", "threads"),
    ("pair-body", "bodySource"),
    ("review", "checkinFrequency"),
]


def _onboarding_state(user_id: int) -> dict:
    s = db.get_app_settings(user_id) or {}
    answers = s.get("onboarding_answers") or {}
    if s.get("onboarding_completed"):
        step = "done"
    else:
        step = next((st for st, key in _ONBOARDING_STEPS if key not in answers), "done")
    return {"step": step, "answers": answers}


class OnboardingAnswer(BaseModel):
    """POST /onboarding/answer body: { step, answer } where answer is a partial."""
    step: str
    answer: dict


@app.get("/api/onboarding/state")
async def get_onboarding_state(user_id: int = Depends(get_current_user_id)):
    """Return the current OnboardingState (step + merged answers)."""
    return _onboarding_state(user_id)


@app.post("/api/onboarding/answer")
async def answer_onboarding(payload: OnboardingAnswer, user_id: int = Depends(get_current_user_id)):
    """Merge an answer into the stored answers, mirroring name/threads to prefs."""
    s = db.get_app_settings(user_id) or {}
    answers = dict(s.get("onboarding_answers") or {})
    answers.update(payload.answer)
    fields = {"onboarding_answers": answers}
    if "name" in payload.answer:
        fields["name"] = payload.answer["name"]
    if "threads" in payload.answer:
        fields["threads"] = payload.answer["threads"]
    db.upsert_app_settings(user_id, **fields)
    return _onboarding_state(user_id)


@app.post("/api/onboarding/complete")
async def complete_onboarding(user_id: int = Depends(get_current_user_id)):
    """Mark onboarding complete and return the configured `User`."""
    db.upsert_app_settings(user_id, onboarding_completed=True)
    return _user_to_contract(user_id)


# ============================================================================
# INSIGHTS ENDPOINTS (single-user; engine outputs → InsightSummary/InsightDetail)
# ============================================================================

class InsightSnooze(BaseModel):
    """POST /insights/:id/snooze body."""
    days: int = 30


@app.get("/api/insights")
async def list_insights(user_id: int = Depends(get_current_user_id)):
    """Return InsightSummary[] from the analytical engines (snoozed/resolved hidden)."""
    return InsightsService(user_id).list_summaries()


@app.get("/api/insights/{insight_id}")
async def get_insight_detail(insight_id: str, user_id: int = Depends(get_current_user_id)):
    """Return the InsightDetail for one engine-derived insight."""
    detail = InsightsService(user_id).get_detail(insight_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    db.mark_insight_seen(user_id, insight_id)
    return detail


@app.post("/api/insights/{insight_id}/snooze")
async def snooze_insight(insight_id: str, body: InsightSnooze, user_id: int = Depends(get_current_user_id)):
    """Snooze an insight for N days; returns the updated InsightSummary."""
    service = InsightsService(user_id)
    summary = service.get_summary(insight_id, force_status="snoozed")
    if summary is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    db.set_insight_status(user_id, insight_id, "snoozed",
                          datetime.now(UTC) + timedelta(days=body.days))
    return summary


@app.post("/api/insights/{insight_id}/resolve")
async def resolve_insight(insight_id: str, user_id: int = Depends(get_current_user_id)):
    """Resolve (dismiss) an insight; returns the updated InsightSummary."""
    service = InsightsService(user_id)
    summary = service.get_summary(insight_id, force_status="resolved")
    if summary is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    db.set_insight_status(user_id, insight_id, "resolved")
    return summary


@app.post("/api/insights/{insight_id}/suggestions/{suggestion_id}/accept")
async def accept_insight_suggestion(insight_id: str, suggestion_id: str,
                                    user_id: int = Depends(get_current_user_id)):
    """Accept a suggestion. No server-side action wired this pass (no-op, 204)."""
    return Response(status_code=204)


# ============================================================================
# REVIEW ENDPOINTS (single-user; weekly aggregation + LLM letter)
# ============================================================================

def _mood_word(mood) -> str:
    """A single-word descriptor for a day's mood (1-10)."""
    if not mood:
        return "quiet"
    if mood >= 8:
        return "bright"
    if mood >= 6:
        return "steady"
    if mood >= 4:
        return "mixed"
    return "heavy"


def _avg_energy(reflections) -> float:
    energies = [r["energy_level"] for r in reflections if r.get("energy_level")]
    return round(sum(energies) / len(energies), 1) if energies else 0.0


def _build_review_week(user_id: int, week_start: date) -> dict:
    """Assemble the frontend `ReviewWeek` from reflections, habits, and themes.

    Sleep/HRV metrics are 0/omitted — there is no body data source (by design)."""
    week_end = week_start + timedelta(days=6)
    service = ReflectionService(user_id)

    this_week = service.get_reflections(start_date=week_start, end_date=week_end)
    prev_week = service.get_reflections(
        start_date=week_start - timedelta(days=7),
        end_date=week_start - timedelta(days=1),
    )
    mood_avg = _avg_energy(this_week)
    mood_delta = round(mood_avg - _avg_energy(prev_week), 1)
    wins = sum(1 for r in this_week if (r.get("energy_level") or 0) >= 7)

    # Daily mood by date (latest reflection's energy that day).
    by_date = {}
    for r in this_week:
        d = r["reflection_date"]
        if r.get("energy_level"):
            by_date.setdefault(d, r["energy_level"])
    days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        mood = by_date.get(d, 0)
        days.append({
            "date": d.isoformat(),
            "shortName": d.strftime("%a").lower(),
            "mood": mood,
            "sleepHours": 0,
            "word": _mood_word(mood),
        })

    # Habits hit this week.
    tracker = HabitTracker(user_id)
    habits = tracker.get_habits(active_only=True)
    habits_hit = 0
    for h in habits:
        comps = db.get_habit_completions(h["id"], week_start, week_end)
        if any(c.get("is_completed") for c in comps):
            habits_hit += 1

    themes_list = [t["summary"] for t in db.get_themes(user_id)[:3] if t.get("summary")]

    # Lookahead from configured check-in times.
    settings = db.get_app_settings(user_id) or {}
    lookahead = []
    if settings.get("weekly_review_time"):
        lookahead.append({"when": settings["weekly_review_time"], "what": "Weekly review"})
    if settings.get("daily_checkin_time"):
        lookahead.append({"when": f"Daily {settings['daily_checkin_time']}", "what": "Check-in"})

    letter = _generate_review_letter(
        user_id, week_start, week_end, mood_avg, mood_delta,
        habits_hit, len(habits), wins, themes_list, days,
    )

    week = {
        "weekStart": week_start.isoformat(),
        "weekEnd": week_end.isoformat(),
        "letter": letter,
        "metrics": {
            "moodAvg": mood_avg,
            "moodDelta": mood_delta,
            "sleepHoursAvg": 0,
            "sleepDeltaMin": 0,
            "habitsHit": habits_hit,
            "habitsTotal": len(habits),
            "winsLogged": wins,
        },
        "days": days,
        "themes": themes_list,
        "lookahead": lookahead,
    }
    if themes_list and wins:
        week["winThatMattered"] = themes_list[0]
    return week


def _generate_review_letter(user_id, week_start, week_end, mood_avg, mood_delta,
                            habits_hit, habits_total, wins, themes_list, days) -> str:
    """Write IRIS's weekly letter via the LLM (mocked in tests)."""
    import agent.core as core_module
    system = (
        "You are IRIS, a reflective AI companion writing a short weekly letter to the "
        "user. Write 2-3 warm, grounded paragraphs in second person. Use only the data "
        "provided — do not invent events. No bullet points, no headings."
    )
    daily = ", ".join(f"{d['shortName']}:{d['mood']}" for d in days)
    prompt = (
        f"Week {week_start.isoformat()} to {week_end.isoformat()}.\n"
        f"Average mood (1-10): {mood_avg} (change vs last week: {mood_delta}).\n"
        f"Habits hit: {habits_hit} of {habits_total}. Wins logged: {wins}.\n"
        f"Daily mood: {daily}.\n"
        f"Recurring themes: {'; '.join(themes_list) if themes_list else 'none yet'}.\n"
        "Write the letter."
    )
    try:
        intelligence = core_module.Intelligence()
        text = intelligence.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system,
        )
        return text or "This week is still taking shape — not enough yet for a full letter."
    except Exception as e:  # pragma: no cover - defensive (e.g. missing API key)
        logger.warning(f"Review letter generation failed: {e}")
        return "I couldn't write your letter this week, but your numbers are above."


@app.get("/api/review/latest")
async def get_latest_review(user_id: int = Depends(get_current_user_id)):
    """ReviewWeek for the most recent 7-day window ending today."""
    week_start = date.today() - timedelta(days=6)
    return _build_review_week(user_id, week_start)


@app.get("/api/review/week/{start}")
async def get_review_week(start: str, user_id: int = Depends(get_current_user_id)):
    """ReviewWeek for the 7-day window beginning on the given ISO date."""
    try:
        week_start = date.fromisoformat(start)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date (use YYYY-MM-DD)")
    return _build_review_week(user_id, week_start)


# ============================================================================
# SPA FALLBACK (serve client-side routes from the built frontend)
# ============================================================================
# Registered last so it never shadows /api/*, /assets, or /health. Active only
# when the SPA is built (frontend/dist), so dev (Vite on :5173) is unaffected.
if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Return index.html for unknown non-API paths so React Router can route."""
        if full_path.startswith(("api/", "assets/")) or full_path == "health":
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


# ============================================================================
# RUN THE APP (for local testing)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
