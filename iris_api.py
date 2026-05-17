"""
IRIS Multi-User API
This is the HTTP layer that wraps your CLI companion logic.
It handles authentication, routing requests to the right companion instance, and returning responses.
"""

from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime, timedelta, date, UTC
from typing import Optional, Dict, List
import os
from dotenv import load_dotenv
from jose import JWTError, jwt
import hashlib
from contextlib import asynccontextmanager

# Load environment variables
load_dotenv()

# Import the companion system
try:
    from agent.core import PersonalAICompanion
    from agent.database import db
    from agent.trackers.habits import HabitTracker
    from agent.trackers.reflections import ReflectionService
    from agent.pipeline import run_processing_pipeline

    COMPANION_AVAILABLE = True
    print("✓ PersonalAICompanion and db imported successfully")
except ImportError as e:
    COMPANION_AVAILABLE = False
    print(f"✗ ImportError: Could not import core components: {e}")
except Exception as e:
    COMPANION_AVAILABLE = False
    print(f"✗ Error importing PersonalAICompanion: {e}")

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Path to the frontend files
FRONTEND_PATH = os.getcwd()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler for app startup/shutdown"""
    if COMPANION_AVAILABLE:
        print("Initializing database schema...")
        try:
            db.create_schema()
            print("✓ Database schema initialized")
        except Exception as e:
            print(f"✗ Failed to initialize database: {e}")
    yield

# Initialize FastAPI app
app = FastAPI(title="IRIS Companion API", version="0.1.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
async def root():
    """Serve the vanilla JS frontend"""
    if os.path.exists("iris_frontend.html"):
        return FileResponse("iris_frontend.html")
    return {"message": "IRIS API Online. Frontend file not found."}


# ============================================================================
# DATA MODELS
# ============================================================================


class UserSignup(BaseModel):
    """What a user sends when creating an account"""

    username: str
    password: str


class UserLogin(BaseModel):
    """What a user sends when logging in"""

    username: str
    password: str


class TokenResponse(BaseModel):
    """What the API sends back after successful login"""

    access_token: str
    token_type: str
    username: str


class ChatMessage(BaseModel):
    """What a user sends when sending a chat message"""

    message: str
    token: str


class ChatResponse(BaseModel):
    """What the API sends back as a chat response"""

    companion_name: str
    message: str
    timestamp: str
    chat_id: str


# ============================================================================
# HABIT MODELS
# ============================================================================

class HabitCreate(BaseModel):
    """Create a new habit"""
    name: str
    description: Optional[str] = None
    frequency_type: str = "daily"  # daily, weekly, specific_days
    habit_type: str = "completion"  # completion, duration, count
    weekly_target: float = 0
    tracking_metric: Optional[str] = "completion"
    category: Optional[str] = "general"

class HabitUpdate(BaseModel):
    """Update habit fields"""
    name: Optional[str] = None
    description: Optional[str] = None
    habit_type: Optional[str] = None
    weekly_target: Optional[float] = None
    tracking_metric: Optional[str] = None
    is_active: Optional[bool] = None

class HabitCompletion(BaseModel):
    """Log a habit completion"""
    habit_id: int
    value: float = 1.0
    date: Optional[str] = None  # ISO date string, defaults to today
    notes: Optional[str] = None

class HabitSkip(BaseModel):
    """Log a habit skip"""
    habit_id: int
    date: Optional[str] = None  # ISO date string, defaults to today
    reason: Optional[str] = None

class HabitResponse(BaseModel):
    """Habit response model"""
    id: int
    name: str
    description: Optional[str]
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
    energy_level: Optional[int] = None  # 1-10
    clarity_level: Optional[int] = None # 1-10
    tags: Optional[List[str]] = None
    reflection_date: Optional[str] = None  # ISO date string

class ReflectionUpdate(BaseModel):
    """Update reflection fields"""
    content: Optional[str] = None
    energy_level: Optional[int] = None
    clarity_level: Optional[int] = None
    tags: Optional[List[str]] = None

class ReflectionResponse(BaseModel):
    """Reflection response model"""
    id: int
    reflection_date: str
    content: str
    mood: Optional[str]
    energy_level: Optional[int]
    clarity_level: Optional[int]
    tags: Optional[List[str]]
    created_at: str
    updated_at: str


# ============================================================================
# IN-MEMORY STORAGE (temporary - will be replaced with real databases later)
# ============================================================================

# User companions (in memory for now - user_id -> companion_instance)
# This is where we'll store the companion object for each user
companions_db: Dict[str, object] = {}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def create_access_token(username: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT token for a user"""
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.now(UTC) + expires_delta
    to_encode = {"sub": username, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> str:
    """Verify a JWT token and return the username"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(token: str) -> str:
    """Dependency to get the current user from the token in the request header"""
    # In a real FastAPI app, you'd use:
    # from fastapi.security import HTTPBearer, HTTPAuthCredentials
    # But for now, we'll keep it simple
    return verify_token(token)


def get_user_id_from_token(token: str) -> int:
    """Get user_id from username in token"""
    username = verify_token(token)
    user = db.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user["id"]


# ============================================================================
# ROOT & STATIC ENDPOINTS
# ============================================================================

# Mount static assets
if os.path.exists(os.path.join(FRONTEND_PATH, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_PATH, "assets")), name="assets")

@app.get("/")
async def root():
    """Serve the vanilla JS frontend"""
    if os.path.exists(os.path.join(FRONTEND_PATH, "iris_frontend.html")):
        return FileResponse(os.path.join(FRONTEND_PATH, "iris_frontend.html"))
    return {"message": "IRIS API Online. Frontend file not found."}

# Health check
@app.get("/health")
async def health_check():
    """Simple endpoint to check if the API is running"""
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================


@app.post("/api/auth/signup", response_model=TokenResponse)
async def signup(user: UserSignup):
    """Create a new user account"""
    try:
        # Store the user (hashed password hashing is handled inside db.create_user)
        db.create_user(user.username, user.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

    # Create and return a token
    token = create_access_token(user.username)

    return TokenResponse(access_token=token, token_type="bearer", username=user.username)


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(user: UserLogin):
    """Log in an existing user"""
    # Verify user credentials against the database
    db_user = db.verify_user(user.username, user.password)
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create and return a token
    token = create_access_token(user.username)

    return TokenResponse(access_token=token, token_type="bearer", username=user.username)


# ============================================================================
# CHAT ENDPOINTS
# ============================================================================


@app.post("/api/chat/message", response_model=ChatResponse)
async def chat(message_data: ChatMessage):
    """Send a message to the companion"""
    # Verify the token and get the username
    username = verify_token(message_data.token)

    if not COMPANION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Companion system not available")

    try:
        # Create a fresh companion for this user
        # 1. Fetch the user object from the database to get the real user_id
        user = db.get_user(username)
        if not user:
             raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user['id']

        # The companion will connect to the databases and load the user's data
        companion = PersonalAICompanion(user_id=user_id)

        # Process the message through the companion
        iris_response = companion.chat(message_data.message)

    except Exception as e:
        print(f"Error processing message: {e}")
        iris_response = f"I encountered an error processing your message: {str(e)}"

    # Return the response (messages already persisted by companion.chat() -> memory.add_message())
    return ChatResponse(
        companion_name="IRIS",
        message=iris_response,
        timestamp=datetime.now(UTC).isoformat(),
        chat_id=username,
    )


@app.post("/api/chat/history")
async def get_chat_history(request: dict):
    """Get the user's chat history from the database."""
    token = request.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token required")

    username = verify_token(token)
    user = db.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    messages = db.get_chat_history(user["id"], limit=50)

    # Format as user/assistant pairs for frontend compatibility
    formatted = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg["role"] == "user":
            companion_response = ""
            if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                companion_response = messages[i + 1]["content"]
                i += 1
            formatted.append({
                "user_message": msg["content"],
                "companion_response": companion_response,
                "timestamp": msg["created_at"].isoformat() if hasattr(msg["created_at"], "isoformat") else str(msg["created_at"]),
            })
        elif msg["role"] == "assistant":
            # Proactive message (no preceding user message)
            formatted.append({
                "user_message": "",
                "companion_response": msg["content"],
                "timestamp": msg["created_at"].isoformat() if hasattr(msg["created_at"], "isoformat") else str(msg["created_at"]),
            })
        i += 1

    return {"username": username, "messages": formatted}


@app.post("/api/chat/greeting")
async def get_greeting(request: dict):
    """Get a dynamic greeting for the user"""
    token = request.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token required")

    username = verify_token(token)
    user = db.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        companion = PersonalAICompanion(user_id=user['id'])
        greeting = companion.generate_initial_greeting()
        return {"greeting": greeting}
    except Exception as e:
        print(f"Greeting error: {e}")
        return {"greeting": f"Hi {username}, I'm Iris. How are you today?"}


@app.post("/api/chat/proactive")
async def proactive_chat(request: dict):
    """Trigger a proactive comment from IRIS"""
    token = request.get("token")
    action_type = request.get("action_type")
    details = request.get("details", {})

    if not token or not action_type:
        raise HTTPException(status_code=400, detail="Token and action_type required")

    username = verify_token(token)
    user = db.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        companion = PersonalAICompanion(user_id=user['id'])
        iris_response = companion.generate_proactive_comment(action_type, details)
        # Response already persisted by companion.generate_proactive_comment() -> memory.add_message()
        return {"message": iris_response}
    except Exception as e:
        print(f"Proactive error: {e}")
        return {"message": "..."} # Fail silently


# ============================================================================
# HABIT ENDPOINTS
# ============================================================================

@app.get("/api/habits")
async def list_habits(token: str = Query(...)):
    """List all active habits for the user"""
    user_id = get_user_id_from_token(token)
    tracker = HabitTracker(user_id)
    habits = tracker.get_habits(active_only=True)
    return {"habits": habits}

@app.post("/api/habits")
async def create_habit(habit: HabitCreate, background_tasks: BackgroundTasks, token: str = Query(...)):
    """Create a new habit"""
    user_id = get_user_id_from_token(token)
    tracker = HabitTracker(user_id)
    habit_id = tracker.create_habit(
        name=habit.name,
        description=habit.description,
        frequency_type=habit.frequency_type,
        habit_type=habit.habit_type,
        weekly_target=habit.weekly_target,
        tracking_metric=habit.tracking_metric,
        category=habit.category
    )
    
    # Trigger pipeline in background
    if background_tasks:
        background_tasks.add_task(run_processing_pipeline, 'habit', habit_id)
        
    return {"habit_id": habit_id, "message": "Habit created successfully"}

@app.get("/api/habits/today")
async def get_today_habits(token: str = Query(...)):
    """Get today's habit checklist with completion status"""
    user_id = get_user_id_from_token(token)
    tracker = HabitTracker(user_id)
    habits = tracker.get_today_status()
    return {"habits": habits}

@app.get("/api/habits/weekly")
async def get_weekly_summary(token: str = Query(...)):
    """Get weekly habit summary"""
    user_id = get_user_id_from_token(token)
    tracker = HabitTracker(user_id)
    summary = tracker.get_weekly_summary()
    return summary

@app.get("/api/habits/consistency/{days}")
async def get_consistency_report(days: int = 30, token: str = Query(...)):
    """Get consistency report across all habits"""
    
    user_id = get_user_id_from_token(token)
    tracker = HabitTracker(user_id)
    report = tracker.get_consistency_report(days)
    return report

@app.get("/api/habits/{habit_id}")
async def get_habit(habit_id: int, token: str = Query(...)):
    """Get details of a specific habit"""
    user_id = get_user_id_from_token(token)
    tracker = HabitTracker(user_id)
    habit = tracker.get_habit(habit_id)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return habit

@app.put("/api/habits/{habit_id}")
async def update_habit(habit_id: int, updates: HabitUpdate, token: str = Query(...)):
    """Update a habit's properties"""
    user_id = get_user_id_from_token(token)
    tracker = HabitTracker(user_id)
    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")
    
    update_dict = updates.dict(exclude_none=True)
    tracker.update_habit(habit_id, **update_dict)
    return {"message": "Habit updated successfully"}

@app.delete("/api/habits/{habit_id}")
async def delete_habit(habit_id: int, token: str = Query(...)):
    """Delete a habit (soft-delete)"""
    user_id = get_user_id_from_token(token)
    tracker = HabitTracker(user_id)
    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")
    
    tracker.delete_habit(habit_id)
    return {"message": "Habit deleted successfully"}

@app.post("/api/habits/complete")
async def log_completion(completion: HabitCompletion, token: str = Query(...)):
    """Log a habit completion"""
    user_id = get_user_id_from_token(token)
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
async def log_skip(skip: HabitSkip, token: str = Query(...)):
    """Log a habit skip"""
    user_id = get_user_id_from_token(token)
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
async def get_habit_calendar(habit_id: int, start: str, end: str, token: str = Query(...)):
    """Get a calendar view of habit completions in a date range"""
    user_id = get_user_id_from_token(token)
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
async def list_reflections(token: str = Query(...), limit: int = 30):
    """List recent reflections"""
    user_id = get_user_id_from_token(token)
    service = ReflectionService(user_id)
    reflections = service.get_reflections(limit=limit)
    return {"reflections": reflections}

@app.post("/api/reflections")
async def create_reflection(reflection: ReflectionCreate, background_tasks: BackgroundTasks, token: str = Query(...)):
    """Create a new reflection"""
    user_id = get_user_id_from_token(token)
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
        # Trigger pipeline in background
        if background_tasks:
            background_tasks.add_task(run_processing_pipeline, 'reflection', reflection_id)
            
        return {"reflection_id": reflection_id, "message": "Reflection saved successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/reflections/moods")
async def get_mood_trend(token: str = Query(...), days: int = 30):
    """Get mood trend data"""
    user_id = get_user_id_from_token(token)
    service = ReflectionService(user_id)
    trend = service.get_mood_trend(days)
    return trend

@app.get("/api/reflections/summary")
async def get_reflection_summary(token: str = Query(...), days: int = 30):
    """Get comprehensive reflection summary"""
    user_id = get_user_id_from_token(token)
    service = ReflectionService(user_id)
    summary = service.get_reflection_summary(days)
    return summary

@app.get("/api/reflections/tags")
async def get_tags_summary(token: str = Query(...), days: int = 30):
    """Get tags summary from reflections"""
    user_id = get_user_id_from_token(token)
    service = ReflectionService(user_id)
    tags = service.get_tag_summary(days)
    return tags

@app.get("/api/reflections/{reflection_id}")
async def get_reflection(reflection_id: int, token: str = Query(...)):
    """Get a specific reflection"""
    user_id = get_user_id_from_token(token)
    service = ReflectionService(user_id)
    reflection = service.get_reflection(reflection_id)
    
    if not reflection:
        raise HTTPException(status_code=404, detail="Reflection not found")
    
    return reflection

@app.put("/api/reflections/{reflection_id}")
async def update_reflection(reflection_id: int, updates: ReflectionUpdate, token: str = Query(...)):
    """Update a reflection"""
    user_id = get_user_id_from_token(token)
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
async def delete_reflection(reflection_id: int, token: str = Query(...)):
    """Delete a reflection"""
    user_id = get_user_id_from_token(token)
    service = ReflectionService(user_id)
    
    if not service.get_reflection(reflection_id):
        raise HTTPException(status_code=404, detail="Reflection not found")
    
    service.delete_reflection(reflection_id)
    return {"message": "Reflection deleted successfully"}


# ============================================================================
# RUN THE APP (for local testing)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
