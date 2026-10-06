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

export interface JournalCheckin {
  energy?: number | null;
  mood?: number | null;
  sleep_quality?: number | null;
  stress?: number | null;
  focus?: number | null;
}

export interface JournalEntry {
  id: ID;
  userId: ID;
  /** Stored lines. New entries also send `text`. */
  lines: string[];
  /** The stored writing. Markdown when `format` is markdown. */
  text?: string;
  format?: 'plain' | 'markdown' | 'session';
  /** A therapy session's turns, read by the server (ADR-0028). */
  session?: JournalSession | null;
  /** 1–10 self-rated energy at time of entry. */
  energy?: number;
  checkin?: JournalCheckin;
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

// Therapy sessions (ADR-0028). Only the owner's turns can become evidence; the
// therapist's turns and those whose speaker is unclear are context.
export type SessionRole = 'owner' | 'therapist' | 'unclear';

export interface SessionTurn {
  /** Seconds from the start of the recording. */
  at: number;
  label: string;
  role: SessionRole;
  text: string;
}

export interface JournalSession {
  kind: 'therapy';
  /** Local wall time as the owner gave it, "YYYY-MM-DDTHH:MM". */
  startedAt: string | null;
  language: string | null;
  owner: string | null;
  therapist: string | null;
  durationSeconds: number | null;
  turns: SessionTurn[];
}

export interface SessionImport {
  id: ID;
  status: 'staged' | 'importing' | 'imported' | 'discarded';
  kind: 'therapy';
  filename: string | null;
  createdAt: ISODateTime;
  startedAt: string | null;
  language: string | null;
  owner: string | null;
  therapist: string | null;
  speakers: { label: string; segments: number; words: number; role: SessionRole }[];
  segments: number;
  turns: number;
  durationSeconds: number | null;
  /** Lines before the first turn (the transcriber's title and notes), left out. */
  leftOut: number;
  /** What the owner still has to say before the session can be imported. */
  missing: string[];
  alreadyImported: { importId: ID; on: ISODate } | null;
  estimate: { passages: number; indexingDollars: number; readingDollars: number | null; updateDollars?: number | null; text: string } | null;
  reflectionId: ID | null;
  /** The optional pass that tells the speakers apart by voice; it sends the recording, so it has its own click. */
  voices: {
    status: 'none' | 'queued' | 'running' | 'done' | 'failed';
    report: SessionVoicesReport | null;
    error: string | null;
    hasRecording: boolean;
    estimate: { minutes: number; dollars: number; text: string } | null;
  };
}

export interface SessionVoicesReport {
  segments: number;
  heard: number;
  /** Lines the transcript labelled as you or the therapist, where a voice was heard. */
  labelled: number;
  agreed: number;
  /** Labelled lines the voices clearly disagreed with, now marked unsure. */
  contradicted: number;
  /** Uncertain lines now given a speaker, by label. */
  attributed: Record<string, number>;
  doubtful: number;
}

export interface JournalWrite {
  text?: string;
  format?: 'plain' | 'markdown';
  checkin?: JournalCheckin;
  lines?: string[];
  energy?: number;
}

export interface JournalListResponse {
  entries: JournalEntry[];
  nextCursor?: string;
  /** Phrases Iris keeps hearing across the user's writing. */
  recurringPhrases?: { phrase: string; count: number }[];
}

// Writing-derived personal dynamics. Dates are dates of recording, not event dates.
export type AccountVerdictValue = 'yes' | 'no' | 'unsure';
export type PatternVerdictValue = 'rings_true' | 'does_not' | 'unsure';
export type DiscoveryRange = 'all' | '30d' | '90d';
export type EvidenceRef =
  | { kind: 'dynamic'; dynamicId: string; range: DiscoveryRange; snapshot: string }
  | { kind: 'personal_insight'; insightId: string; range: DiscoveryRange; snapshot: string }
  | { kind: 'day'; outcome: DayDifference['outcome']; split: DayDifference['split'];
      range: DiscoveryRange; snapshot: string };

export interface DiscussionPreview {
  ref: EvidenceRef;
  title: string;
  question: string;
  evidence: PatternDetail | InsightDetail | DayDifferenceDetail;
  changed: boolean;
}

export interface Coverage {
  range: DiscoveryRange;
  asOf: ISODate;
  recordedFrom: ISODate | null;
  recordedTo: ISODate | null;
  entryCount: number;
  accountCount: number;
  undatedAccountCount: number;
}

export interface Feedback<V> {
  verdict: V | null;
  note: string | null;
}
export type PatternVerdict = Feedback<PatternVerdictValue>;
export interface SavedFeedback<V> extends Feedback<V> {
  updatedAt: ISODateTime;
  needsReview: boolean;
}
export interface FeedbackRequest<V> extends Feedback<V> {
  range: DiscoveryRange;
  snapshot: string;
}

export interface DiscoveryStatus {
  readerVersion: string;
  discoveryVersion: string;
  interpretationVersion: string;
  libraryVersion: string | null;
  model: string;
  stage: 'reading' | 'discovering' | 'checking' | 'interpreting' | 'ready' | 'failed';
  eligibleEntries: number;
  currentEntries: number;
  unreadEntries: number;
  pendingEntries: number;
  failedEntries: number;
  excludedEntries: number;
  omittedAccounts: number;
  omittedFields: number;
  synthesisPending: boolean;
  synthesisFailed: boolean;
  lastCompletedAt: ISODateTime | null;
  estimate: { readingRequests: number; synthesisRequests: number; tokensIn: number;
    tokensOut: number; costText: string; approximate: true };
}

export interface QuoteRef { accountId: string; field: string; citationIndex: number }
export interface GroundedClause { text: string; refs: QuoteRef[] }
export interface Hypothesis {
  text: string;
  premises: GroundedClause[];
  scopeGroupIds: string[];
  ownerReportIds: string[];
}
export interface AccountCitation {
  entryId: ID;
  sourceType: string;
  entryDate: ISODate | null;
  text: string;
}
export interface PersonalAccount {
  id: string;
  actor: 'self' | 'other' | 'unclear';
  recordKind: 'event' | 'self_report' | 'intention' | 'hypothetical';
  situation: string | null;
  response: string | null;
  demand: string | null;
  information: string | null;
  feeling: string | null;
  concern: string | null;
  immediateOutcome: string | null;
  laterOutcome: string | null;
  explanation: string | null;
  selfReport: string | null;
  domain: string | null;
  recordedOn: ISODate | null;
  citations: AccountCitation[];
}
export interface Membership {
  dynamicId: string;
  accountId: string;
  groupId: string | null;
  role: 'support' | 'exception' | 'response_elsewhere' | 'unrelated' | 'unclear' | 'mixed';
  contextDecision: 'present' | 'absent' | 'unclear';
  responseDecision: 'present' | 'absent' | 'unclear';
  relationDecision: 'linked' | 'contradicted' | 'unclear';
  refs: QuoteRef[];
  ownerVerdict: AccountVerdictValue | null;
  verdictNote: string | null;
  excluded: boolean;
}
export interface EventGroup {
  id: string;
  accountIds: string[];
  role: Membership['role'];
  independentlyCountable: boolean;
  independenceUncertain: boolean;
}
export interface ProcessLens {
  id: string;
  family: 'belonging' | 'uncertainty' | 'self_worth' | 'emotional_protection' | 'capacity' | 'agency';
  name: string;
  sequence: string;
  possibleFunction: string;
  immediateReturn: string;
  possibleLaterCost: string;
  requires: [string, string];
  notWhen: string;
  alternative: string;
  question: string;
  sourceIds: string[];
  sources: { id: string; title: string; url: string;
    kind: 'research_article' | 'theoretical_overview'; scope: string }[];
}
export interface PersonalPattern {
  id: string;
  title: string;
  context: GroundedClause;
  response: GroundedClause;
  evidenceState: 'owner_described' | 'emerging' | 'recurring';
  ownerMeanings: GroundedClause[];
  immediateReturn: GroundedClause | null;
  laterCost: GroundedClause | null;
  possibleMeaning: Hypothesis | null;
  alternative: Hypothesis | null;
  openQuestion: string;
  lensMatches: { lensId: string; qualifyingGroupIds: string[]; selfReportIds: string[];
    requirementRefs: QuoteRef[]; excludedGroupIds: string[] }[];
  exceptionGroupIds: string[];
  responseElsewhereGroupIds: string[];
  independentGroupCount: number;
  accountCount: number;
  entryCount: number;
  recordedFrom: ISODate | null;
  recordedTo: ISODate | null;
  undatedAccountCount: number;
  exceptionCount: number;
  unknownAccountCount: number;
  example: { accountId: string; recordedOn: ISODate | null; citation: AccountCitation } | null;
  range: DiscoveryRange;
  asOf: ISODate;
  claimHash: string;
  snapshot: string;
  feedback: SavedFeedback<PatternVerdictValue> | null;
}
export interface PatternDetail {
  pattern: PersonalPattern;
  accounts: Record<string, PersonalAccount>;
  memberships: Record<string, Membership[]>;
  groups: Record<string, EventGroup[]>;
  lenses: ProcessLens[];
  checks: { checked: number; unclear: number; omittedAccounts: number;
    omittedFields: number; exceptionSearchComplete: boolean };
  coverage: Coverage;
  status: DiscoveryStatus;
  snapshot: string;
}
export type InsightKind = 'function_and_tradeoff' | 'contextual_difference' | 'shared_concern';
export interface PersonalInsight {
  id: string;
  kind: InsightKind;
  dynamicIds: string[];
  title: string;
  observation: GroundedClause;
  possibleMeaning: Hypothesis;
  alternative: Hypothesis;
  immediateReturn: GroundedClause | null;
  laterCost: GroundedClause | null;
  supportingGroups: string[];
  contraryGroups: string[];
  unknownAccountIds: string[];
  question: string;
  leftLabel: string | null;
  rightLabel: string | null;
  leftGroupIds: string[] | null;
  rightGroupIds: string[] | null;
  range: DiscoveryRange;
  asOf: ISODate;
  claimHash: string;
  snapshot: string;
  feedback: SavedFeedback<PatternVerdictValue> | null;
}
export interface InsightDetail {
  insight: PersonalInsight;
  accounts: Record<string, PersonalAccount>;
  memberships: Record<string, Membership[]>;
  groups: Record<string, EventGroup[]>;
  coverage: Coverage;
  status: DiscoveryStatus;
  snapshot: string;
}

export interface DayCoverage {
  range: DiscoveryRange;
  asOf: ISODate;
  recordedFrom: ISODate;
  recordedTo: ISODate;
  measuredDays: number;
  checkinDays: number;
  overlappingDays: number;
}

export interface DayDiagnostics {
  measuredDays: number;
  checkinDays: number;
  overlappingDays: number;
  eligibleComparisons: number;
  reason: 'no_measured_days' | 'no_checkins' | 'no_overlap'
    | 'insufficient_groups' | 'no_qualifying_difference' | null;
}

export interface ContributingDay {
  day: ISODate;
  value: number;
  splitValue: number | string;
  entryIds: ID[];
}

export interface DayDifferenceDetail {
  difference: DayDifference;
  leftDays: ContributingDay[];
  rightDays: ContributingDay[];
  excluded: Record<'missingScore' | 'missingMeasurement' | 'lowCoverage' | 'partialSteps' | 'medianTies', number>;
}

/** A comparison of outcome ratings on two groups of measured days, not a cause. */
export interface DayDifference {
  outcome: 'energy' | 'mood' | 'sleep_quality' | 'stress' | 'focus';
  split: 'office_home' | 'commute' | 'steps' | 'screen_time' | 'social_share' | 'sleep';
  sentence: string;
  leftCount: number;
  rightCount: number;
  leftMean: number;
  rightMean: number;
  pValue: number;
  verdict: PatternVerdict | null;
  leftLabel: string;
  rightLabel: string;
  threshold: number | null;
  coverage: DayCoverage;
  snapshot: string;
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
// Noticed — patterns IRIS found by reading, for you to confirm or reject
// ─────────────────────────────────────────────────────────────────────────────

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
/** `life` is a principle the owner states as holding across areas, never one IRIS generalised. */
export type IdeaDomain = 'philosophy' | 'economics' | 'markets' | 'politics' | 'ethics' | 'learning' | 'life' | 'other';
/** `same_meaning`: one essential meaning in different words or fields. It has no direction. */
export type LinkKind = 'supports' | 'contradicts' | 'refines' | 'depends_on' | 'same_meaning' | 'applies';
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
  kind: 'discovery' | 'links' | 'meaning';
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

/** What a same-meaning pass would send (accepted statements only) and cost. */
export interface MeaningEstimate {
  ideas: number;
  calls: number;
  tokensIn: number;
  estimate: string;
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
  /** Quotes waiting for a decision. */
  citations: IdeaCitation[];
  /** Quotes already accepted for this idea, to judge the new ones against. */
  onRecord: IdeaCitation[];
}

export interface IdeasReview {
  ideas: IdeaReviewCard[];
  links: IdeaLink[];
  lastRun: IdeaRun | null;
}

/** The owner's own page for an idea: notes in Markdown, with `[[wording]]` links to other ideas. */
export interface IdeaPage {
  notes: string;
  notesUpdatedAt: ISODateTime | null;
  /** Each `[[target]]` in the notes that names an idea, and that idea's id. */
  links: Record<string, ID>;
  /** Ideas whose notes link here. */
  backlinks: { id: ID; statement: string; status: IdeaStatus }[];
}

export interface IdeaDetail {
  idea: IdeaSummary;
  citations: IdeaCitation[];
  links: IdeaLink[];
  critiques: IdeaCritique[];
  page: IdeaPage;
}

export interface UpdateIdeaBody {
  position?: IdeaPosition;
  domain?: IdeaDomain;
  statement?: string;
  notes?: string;
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

// The baseline questionnaire (ADR-0029). The questions live on this machine only.
export type QuestionStatus = 'unanswered' | 'draft' | 'added' | 'skipped';

export interface InterviewTurn { role: 'iris' | 'owner'; text: string }

export interface QuestionnaireQuestion {
  id: string;
  number: number;
  text: string;
  textPl: string;
  status: QuestionStatus;
  answer: string;
  /** `suggested`: the owner's own sentences, quoted from their writing by IRIS. */
  source: 'form' | 'interview' | 'suggested' | null;
  transcript: InterviewTurn[] | { quotes: string[] } | null;
  /** A draft over an answer already added: a revision waiting to be added. */
  revising: boolean;
  addedAt: ISODateTime | null;
  /** How many answers to this question have been added over time. */
  history: number;
}

export interface QuestionnaireSection {
  id: string;
  title: string;
  titlePl: string;
  intro: string;
  introPl: string;
  questions: QuestionnaireQuestion[];
  counts: Record<QuestionStatus, number> & { total: number };
}

export interface Questionnaire {
  id: string;
  title: string;
  titlePl: string;
  version: string | null;
  about: string | null;
  aboutPl: string | null;
  sections: QuestionnaireSection[];
}

export interface InterviewStep { reply: string; done: boolean; draft: string; skipped: boolean }
