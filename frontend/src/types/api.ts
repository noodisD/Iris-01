/**
 * Iris / Iris — API contract types
 *
 * This file is the source of truth for what data crosses the wire between
 * frontend and backend. Backend should mirror these shapes (or generate
 * them from the same schema source).
 *
 * Conventions:
 *  - All timestamps are ISO 8601 strings (`"2026-05-27T19:42:00Z"`).
 *  - All IDs are opaque strings, generated server-side.
 *  - All "score" values are 0–1 unless otherwise noted (use `unknown`-safe parsing).
 *  - Currency-free: this is a wellness product.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Common / scalar
// ─────────────────────────────────────────────────────────────────────────────

export type ID = string;
export type ISODateTime = string;
export type ISODate = string; // YYYY-MM-DD

/** A 0..1 confidence score for any Iris inference. */
export type Confidence = number;

export type OrbVibe = 'calm' | 'low' | 'high' | 'cool' | 'dim';
export type Tone = 'clinical' | 'warm' | 'playful';
export type Density = 'sparse' | 'balanced' | 'dense';

// ─────────────────────────────────────────────────────────────────────────────
// User
// ─────────────────────────────────────────────────────────────────────────────

export interface User {
  id: ID;
  name: string;
  email?: string;
  createdAt: ISODateTime;
  /** Days since user joined; computed server-side. */
  dayInJourney: number;
  timezone: string;            // e.g. "America/Los_Angeles"
  preferences: UserPreferences;
}

export interface UserPreferences {
  tone: Tone;
  density: Density;
  dailyCheckinTime?: string;   // "19:30"
  weeklyReviewTime?: string;   // "Sun 09:00"
  maxNudgesPerDay: number;     // default 1
  threadsListenedFor: ThreadKey[];
}

export type ThreadKey =
  | 'mood' | 'energy' | 'sleep' | 'habits'
  | 'topics' | 'worries' | 'wins'
  | 'social' | 'focus' | 'meals';

// ─────────────────────────────────────────────────────────────────────────────
// Chat / conversation
// ─────────────────────────────────────────────────────────────────────────────

export type ChatRole = 'user' | 'iris' | 'system';

export interface ChatMessage {
  id: ID;
  conversationId: ID;
  role: ChatRole;
  /** Plain text. Markdown rendering is a frontend concern. */
  text: string;
  createdAt: ISODateTime;
  /** Tag terms Iris "noticed" while writing this message. */
  noticed?: NoticedTag[];
  /** Optional structured quick-reply options Iris is offering. */
  quickReplies?: QuickReply[];
  /** True while a partial reply is still streaming. */
  streaming?: boolean;
}

export interface NoticedTag {
  /** Stable key like `tuesdays_standup`. */
  key: string;
  label: string;
  confidence: Confidence;
}

export interface QuickReply {
  id: string;
  label: string;
  /** Optional action keyword the backend can interpret. */
  intent?: string;
}

export interface Conversation {
  id: ID;
  userId: ID;
  startedAt: ISODateTime;
  lastMessageAt: ISODateTime;
  messageCount: number;
  /** Inferences Iris is currently holding from this conversation. */
  inferred: InferredItem[];
}

export interface InferredItem {
  tag: string;             // e.g. "mood", "energy", "win"
  value: string;           // e.g. "tired · relieved"
  confidence: Confidence;
  derivedFrom: ('text' | 'air' | 'health-connect' | 'apple-health' | 'calendar' | 'pattern')[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Journal
// ─────────────────────────────────────────────────────────────────────────────

export interface JournalEntry {
  id: ID;
  userId: ID;
  /** "Three-line" prompts; UI shows 3 but backend should accept N. */
  lines: string[];
  /** 1–10 self-rated mood at time of entry. */
  mood?: number;
  /** Server-extracted tags; frontend never invents these. */
  tags?: string[];
  irisNote?: string;        // What Iris observed about this entry
  createdAt: ISODateTime;
}

export interface JournalListResponse {
  entries: JournalEntry[];
  nextCursor?: string;
  /** Phrases Iris keeps hearing across the user's writing. */
  recurringPhrases?: { phrase: string; count: number }[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Habits
// ─────────────────────────────────────────────────────────────────────────────

export interface Habit {
  id: ID;
  userId: ID;
  name: string;
  /** Short cadence string for the UI: "10 min · morning". */
  tag: string;
  /** What the user said they're trying to address. */
  intent?: string;
  /** Theme color: 'sage' | 'amber' | 'indigo' | 'rose' | … or a hex. */
  color: string;
  /** Habit IDs this habit tends to enable, observed empirically. */
  supports: ID[];
  /** Convenience: streak length in days. */
  streakDays: number;
  bestStreak: number;
  doneToday: boolean;
  /**
   * Recent completion history, oldest → newest.
   * Length = days covered (e.g. 60). 1 = done, 0 = skipped.
   */
  recentDays: (0 | 1)[];
}

export interface HabitsTodayResponse {
  habits: Habit[];
  /** Aggregate stats for today. */
  doneCount: number;
  totalCount: number;
  /** 30-day consistency in 0..1. */
  consistency30d: number;
  longestActiveStreak: number;
  /** Optional Iris nudge to render at the top. */
  suggestion?: IrisSuggestion;
}

export interface IrisSuggestion {
  id: ID;
  kind: 'new-habit' | 'auto-mute' | 'reframe' | 'pre-write';
  text: string;
  /** What the user gets if they accept. */
  payload?: Record<string, unknown>;
}

export interface HabitToggleRequest {
  habitId: ID;
  done: boolean;
  /** Optional: the date being toggled (defaults to today on server). */
  date?: ISODate;
}

// ─────────────────────────────────────────────────────────────────────────────
// Body — Fitbit Air / Health Connect / Apple Health
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// Insights — patterns Iris found
// ─────────────────────────────────────────────────────────────────────────────

export type InsightKind =
  | 'fusion'        // body + words
  | 'temporal'      // day-of-week, time-of-day
  | 'causal'        // X → Y over time
  | 'linguistic'    // word patterns
  | 'embodied';     // body-vocabulary

export type InsightStatus = 'new' | 'active' | 'snoozed' | 'resolved';

export interface InsightSummary {
  id: ID;
  kind: InsightKind;
  status: InsightStatus;
  /** Three-line headline. Frontend renders frag1 / frag2 / frag3 styled. */
  headline: { line1: string; line2: string; line3: string };
  summary: string;
  /** 'sage' | 'rose' | 'indigo' | 'amber' — used as a theme color. */
  accentColor: string;
  featured: boolean;
  tags: string[];
  confidence: Confidence;
  detectedAt: ISODateTime;
  /** Has the user actually opened this? */
  seen: boolean;
}

export interface InsightDetail extends InsightSummary {
  /** Rich body for the deep-dive page. */
  irisRead: string;
  /** Evidence series — typed loosely so backend can ship different shapes. */
  evidence: InsightEvidence[];
  pullQuotes: { sourceDate: ISODate; text: string; sourceKind: 'journal' | 'chat' }[];
  related: { id: ID; label: string; tag: string }[];
  /** "Things to try" — clickable, optionally trigger server actions. */
  suggestions: InsightSuggestion[];
  /** Free-form methodology paragraph the user can expand. */
  methodology: string;
}

export type InsightEvidence =
  | { kind: 'twin-series'; label: string; series: { name: string; color: string; points: { x: string; y: number }[] }[] }
  | { kind: 'heatmap'; label: string; rows: string[]; cols: string[]; values: number[][] }
  | { kind: 'comparison'; label: string; items: { label: string; value: number; sub?: string }[] }
  | { kind: 'callout'; label: string; value: string; sub?: string };

export interface InsightSuggestion {
  id: ID;
  label: string;
  impact: string;
  /** If set, accepting POSTs an action to this path. */
  acceptUrl?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Settings — what Iris knows + data sources
// ─────────────────────────────────────────────────────────────────────────────

export interface KnownFact {
  id: ID;
  fact: string;
  source: 'chat' | 'journal' | 'pattern' | 'derived' | 'air' | 'language' | 'fusion';
  /** Days since Iris learned it. */
  ageDays: number;
  /** Can the user edit/forget this one? Usually yes. */
  editable: boolean;
}

export interface DataConnector {
  id: 'fitbit-air' | 'google-health' | 'apple-health' | 'calendar' | 'spotify' | 'photos' | 'messages' | 'location';
  name: string;
  /** What we read; shown in UI for transparency. */
  scopeDescription: string;
  state: 'connected' | 'paused' | 'off';
  featured?: boolean;     // marked "primary biosignal" in UI
  /** OAuth flow URL if applicable. */
  connectUrl?: string;
  disconnectUrl?: string;
  lastSyncedAt?: ISODateTime;
}

// ─────────────────────────────────────────────────────────────────────────────
// Review — weekly / monthly
// ─────────────────────────────────────────────────────────────────────────────

export interface ReviewWeek {
  weekStart: ISODate;
  weekEnd: ISODate;
  /** Iris's longform letter, rendered as serif paragraphs in the UI. */
  letter: string;
  metrics: {
    moodAvg: number;
    moodDelta: number;
    sleepHoursAvg: number;
    sleepDeltaMin: number;
    habitsHit: number;
    habitsTotal: number;
    winsLogged: number;
    hrvDeltaMs?: number;
  };
  days: ReviewDay[];
  themes: string[];               // up to 3
  winThatMattered?: string;
  strugglesLingering?: string;
  lookahead: { when: string; what: string }[];
}

export interface ReviewDay {
  date: ISODate;
  shortName: string;              // "mon"
  mood: number;                   // 1..10
  sleepHours: number;
  /** A single word for the day — Iris's choice. */
  word: string;
  /** Optional one-line headline (used in dense layout). */
  headline?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Onboarding
// ─────────────────────────────────────────────────────────────────────────────

export interface OnboardingState {
  step:
    | 'hello' | 'name' | 'reason' | 'threads'
    | 'pair-body' | 'review' | 'done';
  answers: Partial<{
    name: string;
    reason: string;
    threads: ThreadKey[];
    bodySource: 'fitbit-air' | 'apple-health' | 'health-connect' | 'none';
    checkinFrequency: 'once' | 'twice';
  }>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Errors
// ─────────────────────────────────────────────────────────────────────────────

export interface ApiError {
  /** Stable machine code, e.g. "unauthorized", "rate_limited". */
  code: string;
  /** Human-readable message — safe to display. */
  message: string;
  /** Optional field-level errors for forms. */
  fields?: Record<string, string>;
}
