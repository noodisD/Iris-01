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
  /** True while a partial reply is still streaming. */
  streaming?: boolean;
}

export interface Conversation {
  id: ID;
  userId: ID;
  startedAt: ISODateTime;
  lastMessageAt: ISODateTime;
  messageCount: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Journal
// ─────────────────────────────────────────────────────────────────────────────

export interface JournalEntry {
  id: ID;
  userId: ID;
  /** "Three-line" prompts; UI shows 3 but backend should accept N. */
  lines: string[];
  /** 1–10 self-rated energy at time of entry. */
  energy?: number;
  /** Server-extracted tags; frontend never invents these. */
  tags?: string[];
  irisNote?: string;        // What Iris observed about this entry
  /** The day the entry was written, or null when it is not known. Imported
   *  entries keep their own date; an undated recording stays undated. */
  occurredOn: ISODate | null;
  /** When the row reached IRIS — the import day for an imported entry. */
  importedAt?: ISODateTime;
  /** The same day as `occurredOn`; null when that is unknown. */
  createdAt: ISODateTime | null;
  /** The recording this entry was transcribed from, where one was kept. */
  audioUrl?: string | null;
}

export interface JournalListResponse {
  entries: JournalEntry[];
  nextCursor?: string;
  /** Phrases Iris keeps hearing across the user's writing. */
  recurringPhrases?: { phrase: string; count: number }[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Patterns — discovery: library patterns, the occasions that are instances of them
// ─────────────────────────────────────────────────────────────────────────────

/** How an occasion turned out, as the labelling pass read it. */
export type OccasionTone = 'better' | 'worse' | 'mixed';
export type OccasionVerdictValue = 'yes' | 'no' | 'unsure';
export type PatternVerdictValue = 'rings_true' | 'does_not' | 'unsure';

export interface PatternInfo {
  id: string;
  name: string;
  statement: string;
  holdsWhen: string[];
  notWhen: string[];
  question: string;
  basis: string | null;
  /** How well the idea behind it has held up: 'well replicated' | 'mixed' | 'contested'. */
  evidence: string | null;
  source: string | null;
}

export interface PatternVerdict {
  verdict: PatternVerdictValue;
  note: string | null;
}

export interface PatternSummary extends PatternInfo {
  /** Occasions, not counting any you said are not this pattern. */
  occasions: number;
  tones: Record<OccasionTone, number>;
  reviewed: number;
  rejected: number;
  /** What produced the labels. Labellers miss some occasions and include some that do not belong. */
  labelledBy: string[];
  verdict: PatternVerdict | null;
}

export interface OccasionCitation {
  entryId: ID;
  sourceType: string;
  entryDate: string | null;
  text: string;
}

export interface Occasion {
  id: ID;
  occurredOn: string | null;
  domain: string | null;
  situation: string;
  response: string;
  outcome: string | null;
  explanation: string | null;
  citations: OccasionCitation[];
  tone: OccasionTone;
  size: string | null;
  labelledBy: string | null;
  ownerVerdict: OccasionVerdictValue | null;
  verdictNote: string | null;
}

export interface PatternDetail {
  pattern: PatternInfo;
  occasions: Occasion[];
  /** Other patterns also present on each side, and on how many occasions. */
  alsoTrue: Record<'better' | 'worse', Record<string, number>>;
  /** Differences of two or more between the sides. Not causes: differences. */
  distinctive: { patternId: string; name: string; better: number; worse: number }[];
  verdict: PatternVerdict | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Decisions — a decision journal, filled in when a decision is made
// ─────────────────────────────────────────────────────────────────────────────

export type Stake = 'little' | 'fair' | 'a_lot' | 'beyond_means';
export type Reversible = 'easily' | 'at_a_cost' | 'not_at_all';
/** What the days before held. */
export type LastDays = 'setback' | 'success' | 'neither';
export type Pressure = 'deadline' | 'money' | 'people' | 'urge';
export type Feeling = 'calm' | 'excited' | 'anxious' | 'frustrated';
export type FollowedPlan = 'yes' | 'partly' | 'no';
export type WouldRepeat = 'yes' | 'no' | 'unsure';

export interface Decision {
  id: ID;
  /** The day it was made (YYYY-MM-DD, a day not an instant). */
  decidedOn: string;
  what: string;
  stake: Stake | null;
  reversible: Reversible | null;
  /** How sure, 0–100. */
  confidence: number | null;
  lastDays: LastDays | null;
  /** What was pushing for a decision now; empty means nothing was. */
  pressures: Pressure[];
  sleepHours: number | null;
  /** 1–10, like the journal's energy. */
  energy: number | null;
  feeling: Feeling | null;
  /** What would make you stop or change course. */
  plan: string | null;
  /** Filled in later. `closedAt` is set the first time it is. */
  outcome: string | null;
  followedPlan: FollowedPlan | null;
  /** Whether you would decide the same again — not whether it went well. */
  wouldRepeat: WouldRepeat | null;
  closedAt: string | null;
}

export type DecisionCreate = Pick<Decision, 'what'> & Partial<Omit<Decision,
  'id' | 'what' | 'outcome' | 'followedPlan' | 'wouldRepeat' | 'closedAt'>>;

export interface DecisionOutcome {
  outcome: string;
  followedPlan?: FollowedPlan | null;
  wouldRepeat?: WouldRepeat | null;
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
// Insights — patterns Iris found
// ─────────────────────────────────────────────────────────────────────────────

/** Which measurement a finding is, in words: agent/insights_service.py KIND_MAP.
 *  Nothing here is causal — "which comes first" is order, not influence. */
export type InsightKind =
  | 'across the record'         // lifelong
  | 'direction'                 // trajectory
  | 'still here or gone quiet'  // resolution
  | 'co-occurrence'             // tension: two themes on the same days
  | 'which comes first'         // leverage
  | 'before and after';         // decision impact

export type InsightStatus = 'new' | 'active' | 'snoozed' | 'resolved';

/** A pattern IRIS noticed by reading, waiting for you to confirm or reject it.
 *  Nothing here is measured by any engine until it is confirmed. */
/** The last archive read, as counts: what it found and why the rest was let go.
 *  Never a claim or a quote. */
export interface DiscoveryRun {
  status: 'running' | 'complete' | 'partial' | 'failed';
  startedAt: ISODateTime;
  finishedAt: ISODateTime | null;
  entriesRead: number;
  passesPlanned: number;
  passesCompleted: number;
  rawFindings: number;
  staged: number;
  dropped: {
    mergedAway: number; unchecked: number; incomplete: number; denied: number;
    tooFewSupporting: number; alreadyDecided: number; notEmbedded: number;
  };
  /** False for runs made before drops were recorded. */
  dropsRecorded: boolean;
}

export interface ConstructCandidate {
  id: ID;
  /** The claim, in the reader's words. */
  claim: string;
  /** A card-sized name for it. */
  summary: string;
  origin: 'observed' | 'clustered';
  /** What confirming it would mean. 'mention' is what a verified quote can
   *  support; 'behaviour' claims the thing happened and is not yet evidenced. */
  claimKind: 'mention' | 'behaviour';
  spanStart: ISODate | null;
  spanEnd: ISODate | null;
  /** The owner's own sentences the claim rests on, verified verbatim. */
  quotes: {
    text: string;
    entryId: ID | null;
    sourceType: string;
    /** False for a staged recording: quotable, but it has no date, so it can
     *  never become an occurrence. */
    citable: boolean;
  }[];
}

/** Why the insights list may be empty: how much recent evidence there is. */
export interface InsightCoverage {
  /** False when the check itself failed — not a measured absence. */
  available: boolean;
  windowDays: number;
  observedDaysInWindow: number;
  /** Days that must be written in before IRIS describes the present. */
  observedDaysRequired: number;
  lastEntryOn: ISODate | null;
  daysSinceLastEntry: number | null;
  supportsCurrentState: boolean;
  entries: number;
  themes: number;
  entriesInThemes: number;
  /** Findings the owner's own confidence filter removed. Null when unknown. */
  suppressedByFilter: number | null;
  /** Admitted findings hidden because they are resolved or still snoozed. */
  hiddenByStatus: number | null;
  /** Findings that passed the admission policy, before status filtering. */
  admitted: number | null;
}

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
  /** How this was arrived at. Absent for findings that span two patterns,
   *  where a single origin would be a fiction. */
  origin?: 'observed' | 'clustered';
  /** 'mention' counts appearances in the writing, never actions taken. */
  claimKind?: 'mention' | 'behaviour';
  /** When the owner vouched for it, if they did. */
  confirmedAt?: ISODateTime | null;
}

export interface InsightDetail extends InsightSummary {
  /** Rich body for the deep-dive page. */
  irisRead: string;
  /** Evidence series — typed loosely so backend can ship different shapes. */
  evidence: InsightEvidence[];
  /** `sourceId` is the journal entry this came from, when it can be opened. */
  pullQuotes: { sourceDate: ISODate; text: string; sourceKind: 'journal' | 'chat'; sourceId?: ID | null }[];
  related: { id: ID; label: string; tag: string }[];
  /** Free-form methodology paragraph the user can expand. */
  methodology: string;
}

export type InsightEvidence =
  | { kind: 'twin-series'; label: string; series: { name: string; color: string; points: { x: string; y: number }[] }[] }
  | { kind: 'heatmap'; label: string; rows: string[]; cols: string[]; values: number[][] }
  | { kind: 'comparison'; label: string; items: { label: string; value: number; sub?: string }[] }
  | { kind: 'callout'; label: string; value: string; sub?: string };

// ─────────────────────────────────────────────────────────────────────────────
// Settings — what Iris knows
// ─────────────────────────────────────────────────────────────────────────────

export interface KnownFact {
  id: ID;
  fact: string;
  /** A cluster the machine found, or a pattern the owner confirmed. */
  source: 'pattern' | 'confirmed';
  /** Days since Iris learned it. */
  ageDays: number;
  /** Can the user edit/forget this one? Usually yes. */
  editable: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Review — weekly / monthly
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The analytical gates: what Iris is *willing to claim*, as opposed to
 * UserPreferences, which is how she says it.
 */
export interface AnalysisPreferences {
  /** Findings below this confidence are not surfaced. */
  minConfidence: 'low' | 'medium' | 'high';
  /** Cap on findings carried into a single conversation. 1-10. */
  maxItems: number;
  /** null means every engine — which is not the same as an empty list. */
  enabledEngines: string[] | null;
  /** Server-supplied, so the UI does not keep its own copy of the engine list. */
  availableEngines: string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Import
// ─────────────────────────────────────────────────────────────────────────────

export interface ImportAdapter {
  name: string;
  label: string;
  description: string;
}

/** How confident we are about an entry's date. Never invented — see occurredOn. */
export type DateConfidence = 'certain' | 'probable' | 'unknown';

export type ImportBatchStatus =
  | 'uploaded' | 'parsing' | 'needs_review' | 'committing' | 'committed' | 'failed';

export type ImportEntryStatus =
  | 'staged' | 'excluded' | 'duplicate' | 'imported' | 'failed';

export interface ImportBatch {
  id: ID;
  kind: 'text' | 'audio';
  /** Which format the upload was read as; overridable. */
  adapter: string | null;
  /** Every format that recognised it, best first. */
  detected: { adapter: string; label: string; score: number }[];
  originalFilename: string | null;
  status: ImportBatchStatus;
  error: string | null;
  entryCount: number;
  committedCount: number;
  createdAt: ISODateTime;
  counts: {
    total: number;
    staged: number;
    excluded: number;
    duplicate: number;
    imported: number;
    failed: number;
    /** Entries with no date. While this is non-zero the import cannot commit. */
    needsDate: number;
    /** Recordings still being transcribed. Also blocks commit — but by waiting,
     *  not by anything the owner has to fix. */
    awaitingTranscript: number;
    earliest: ISODate | null;
    latest: ISODate | null;
  };
}

export interface ImportEntry {
  id: ID;
  sourceName: string | null;
  title: string | null;
  excerpt: string;
  /** null means the date could not be determined and must be supplied. */
  occurredOn: ISODate | null;
  dateSource: string | null;
  dateConfidence: DateConfidence;
  /** The owner looked and said the day is not recoverable. Only these commit
   *  without a date; an entry the parser simply could not date does not. */
  dateUnknownAccepted: boolean;
  /** The day the entry's file was last saved, where the upload carried it.
   *  Offered as a guess for an undated entry; never applied on its own. */
  fileModifiedOn: ISODate | null;
  status: ImportEntryStatus;
  warnings: string[];
  hasAudio: boolean;
  error: string | null;
}

export interface CommitResult {
  committed: number;
  duplicates: number;
  failed: number;
  excluded: number;
}

export interface ReviewWeek {
  weekStart: ISODate;
  weekEnd: ISODate;
  /** Iris's longform letter, rendered as serif paragraphs in the UI. */
  letter: string;
  metrics: {
    /** The energy the owner reported, averaged; null when none was reported. */
    energyAvg: number | null;
    /** Signed change vs the previous week; null when either week has no energy. */
    energyDelta: number | null;
    habitsHit: number;
    habitsTotal: number;
  };
  days: ReviewDay[];
  themes: string[];               // up to 3
  lookahead: { when: string; what: string }[];
}

export interface ReviewDay {
  date: ISODate;
  shortName: string;              // "mon"
  /** The energy the owner reported that day (1..10), or null. */
  energy: number | null;
  /** "6/10", "written" (no energy given) or "no entry" — never a score of IRIS's. */
  word: string;
  /** Optional one-line headline (used in dense layout). */
  headline?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Ideas
// ─────────────────────────────────────────────────────────────────────────────

export type IdeaStatus = 'candidate' | 'active' | 'rejected';
export type IdeaPosition = 'exploring' | 'endorsed' | 'opposed';
export type CitationStance = 'endorsed' | 'questioned' | 'opposed';
export type IdeaDomain = 'philosophy' | 'economics' | 'trading' | 'politics' | 'ethics' | 'learning' | 'other';
export type LinkKind = 'supports' | 'contradicts' | 'refines' | 'depends_on';
export type ReviewStatus = 'candidate' | 'accepted' | 'rejected';

export interface IdeaDropped {
  invalid_quote: number;
  not_stated: number;
  unchecked: number;
  malformed: number;
  already_decided: number;
  duplicate: number;
  source_changed: number;
}

export interface IdeaSummary {
  id: ID;
  statement: string;
  domain: IdeaDomain;
  status: IdeaStatus;
  position: IdeaPosition;
  citationCount: number;
  pendingCitationCount: number;
  firstWrittenOn: ISODate | null;
  lastWrittenOn: ISODate | null;
  undatedCount: number;
  needsEvidence: boolean;
}

export interface IdeaCitation {
  id: ID;
  entryId: ID;
  entryDate: ISODate | null;
  text: string;
  stance: CitationStance;
  status: ReviewStatus;
}

export interface IdeaLink {
  id: ID;
  fromIdeaId: ID;
  toIdeaId: ID;
  kind: LinkKind;
  rationale: string;
  status: ReviewStatus;
  fromStatement: string;
  toStatement: string;
}

export interface IdeaRun {
  id: ID;
  kind: 'discovery' | 'links';
  status: 'running' | 'complete' | 'partial' | 'failed';
  startedAt: ISODateTime;
  finishedAt: ISODateTime | null;
  itemsRead: number;
  passesPlanned: number;
  passesCompleted: number;
  proposed: number;
  dropped: IdeaDropped;
  error: string | null;
}

export interface IdeaCritiqueContent {
  objections: { argument: string; question: string }[];
  possiblePremises: { premise: string; question: string }[];
  relatedThought: { name: string; kind: 'thinker' | 'school'; connection: string }[];
}

export interface IdeaCritique {
  id: ID;
  origin: 'iris';
  createdAt: ISODateTime;
  model: string;
  promptVersion: string;
  basis: unknown;
  content: IdeaCritiqueContent;
  isCurrent: boolean;
}

export interface IdeasFramework {
  ideas: IdeaSummary[];
  links: IdeaLink[];
  tensionIds: ID[];
  foundationIds: ID[];
  unconnectedIds: ID[];
  lastRun: IdeaRun | null;
}

export interface IdeaReviewCard {
  idea: IdeaSummary;
  citations: IdeaCitation[];
}

export interface IdeasReview {
  ideas: IdeaReviewCard[];
  links: IdeaLink[];
  lastRun: IdeaRun | null;
}

export interface IdeaDetail {
  idea: IdeaSummary;
  citations: IdeaCitation[];
  links: IdeaLink[];
  critiques: IdeaCritique[];
}

export interface ConfirmIdeaBody {
  citationIds: ID[];
  position: IdeaPosition;
  domain: IdeaDomain;
}

// ─────────────────────────────────────────────────────────────────────────────
// Onboarding
// ─────────────────────────────────────────────────────────────────────────────

export interface OnboardingState {
  /** First run is one paragraph and one button. */
  step: 'welcome' | 'done';
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
