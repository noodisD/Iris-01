/**
 * Mock data layer.
 *
 * Gated by VITE_USE_MOCKS=true. Lets designers and frontend engineers iterate
 * without a live backend. Each api module checks `useMocks()` and dispatches
 * here. Keep the shapes faithful to types/api.ts — these are the ground truth
 * for what every screen expects.
 */

import type {
  User, ChatMessage, Conversation, InferredItem,
  Habit, HabitsTodayResponse, IrisSuggestion,
  InsightSummary, InsightDetail,
  BodyOverviewResponse, BodyDay,
  JournalEntry, JournalListResponse,
  KnownFact, DataConnector,
  ReviewWeek,
} from '@/types/api';

// ─── Helpers ────────────────────────────────────────────────────────────────

const now = () => new Date().toISOString();
const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();
const dateAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);

// ─── User ───────────────────────────────────────────────────────────────────

export const mockUser: User = {
  id: 'u_sam',
  name: 'Sam Reeves',
  email: 'sam@example.com',
  createdAt: daysAgo(47),
  dayInJourney: 47,
  timezone: 'America/Los_Angeles',
  preferences: {
    tone: 'warm',
    density: 'balanced',
    dailyCheckinTime: '19:30',
    weeklyReviewTime: 'Sun 09:00',
    maxNudgesPerDay: 1,
    threadsListenedFor: ['mood','energy','sleep','habits','topics','wins'],
  },
};

// ─── Conversation / chat ────────────────────────────────────────────────────

export const mockInferred: InferredItem[] = [
  { tag: 'mood',    value: 'tired · relieved',              confidence: 0.84, derivedFrom: ['text'] },
  { tag: 'energy',  value: '38 / 100 (you) · 72 (air)',     confidence: 0.72, derivedFrom: ['text','air'] },
  { tag: 'meals',   value: 'skipped lunch',                 confidence: 0.95, derivedFrom: ['text'] },
  { tag: 'pattern', value: 'tuesday standup overrun',       confidence: 0.66, derivedFrom: ['pattern'] },
  { tag: 'win',     value: 'design review shipped',         confidence: 0.91, derivedFrom: ['text'] },
  { tag: 'hrv',     value: '+9 ms post-3pm · air',           confidence: 0.88, derivedFrom: ['air'] },
];

export const mockConversation: Conversation = {
  id: 'c_today',
  userId: mockUser.id,
  startedAt: now(),
  lastMessageAt: now(),
  messageCount: 7,
  inferred: mockInferred,
};

export const mockMessages: ChatMessage[] = [
  {
    id: 'm1', conversationId: 'c_today', role: 'iris',
    text: "Welcome back, Sam. It's late — 7:42 on a Tuesday. How is the day landing in your body right now?",
    createdAt: now(),
  },
  {
    id: 'm2', conversationId: 'c_today', role: 'user',
    text: "honestly kind of fried. the standup ran over and i didn't eat lunch until 3. been a long one.",
    createdAt: now(),
  },
  {
    id: 'm3', conversationId: 'c_today', role: 'iris',
    text: "That's the third Tuesday in a row standup has eaten through lunch. Last time you mentioned it the word you used was \"depleted.\" Same shape, or different today?",
    createdAt: now(),
    noticed: [
      { key: 'tuesdays_standup', label: 'tuesdays_standup', confidence: 0.66 },
      { key: 'skipped_meals',    label: 'skipped_meals',    confidence: 0.91 },
    ],
  },
  {
    id: 'm4', conversationId: 'c_today', role: 'user',
    text: "different. less anxious. just tired. i did get the design review done though, that was a relief",
    createdAt: now(),
  },
  {
    id: 'm5', conversationId: 'c_today', role: 'iris',
    text: "Your Air agrees — your HRV is up 9ms from yesterday and your breathing rate quieted by 3 PM. The body knew the design review was over before you did.",
    createdAt: now(),
    bio: { hrv: '+9 ms', breath: '−0.8 br/min', rhr: 'steady' },
  },
  {
    id: 'm6', conversationId: 'c_today', role: 'iris',
    text: "Good. You'd been carrying that one for nine days.",
    createdAt: now(),
  },
  {
    id: 'm7', conversationId: 'c_today', role: 'iris',
    text: "Want to log it as a win, or would you rather just sit with the tired for a minute and write three lines about the day?",
    createdAt: now(),
    quickReplies: [
      { id: 'q1', label: 'Log it as a win',    intent: 'add-win' },
      { id: 'q2', label: 'Three lines, please', intent: 'open-journal' },
      { id: 'q3', label: 'Ask me something else' },
    ],
  },
];

/** A stand-in for Mira's reply when the backend isn't wired up. */
export function fakeIrisReply(userText: string, tone: 'clinical' | 'warm' | 'playful'): string {
  const t = userText.toLowerCase();
  const lib = {
    warm: {
      tired: "Tired tracks. Want a soft landing tonight, or a real question?",
      anxious: "I'm here. Where do you feel it — chest, jaw, somewhere else?",
      good: "Hold onto that. What part of today made it feel that way?",
      idk: "That's okay. Sometimes a day just is. What did your hands do today?",
      default: "Mmm. Tell me more.",
    },
    clinical: {
      tired: "Noted: low-energy report. Sleep last night logged at 6h 51m.",
      anxious: "Noted: anxiety self-report. Cross-referencing HRV.",
      good: "Positive affect logged.",
      idk: "Acknowledged. I'll wait.",
      default: "Acknowledged.",
    },
    playful: {
      tired: "Ugh, same energy. Tea or just collapse? 🍃",
      anxious: "I see you. Where's the brain holding it today?",
      good: "Yes! Tell me the thing.",
      idk: "Mood: indeterminate. Permitted. ✨",
      default: "Go on…",
    },
  }[tone];
  if (/tired|fried|exhausted|wiped|drained/.test(t)) return lib.tired;
  if (/anxious|nervous|worried|scared|dread/.test(t)) return lib.anxious;
  if (/good|great|nice|happy|relief|relieved/.test(t)) return lib.good;
  if (/idk|don.?t know|not sure|whatever/.test(t)) return lib.idk;
  return lib.default;
}

// ─── Habits ─────────────────────────────────────────────────────────────────

function dotHistory(seed: number, days = 60): (0 | 1)[] {
  let s = seed;
  return Array.from({ length: days }, (_, i) => {
    s = (s * 9301 + 49297) % 233280;
    const recency = 1 - (i / days) * 0.4;
    return (s / 233280) * recency > 0.45 ? 1 : 0;
  });
}

export const mockHabits: Habit[] = [
  { id: 'h-meditate', userId: mockUser.id, name: 'Meditate',  tag: '10 min · morning',   intent: 'be less reactive at standup', color: 'sage',   supports: ['h-walk'],     streakDays: 14, bestStreak: 23, doneToday: true,  recentDays: dotHistory(7)  },
  { id: 'h-walk',     userId: mockUser.id, name: 'Walk outside', tag: 'noon or after work', intent: 'reset between focus blocks',  color: 'amber',  supports: ['h-phonebed'], streakDays: 9,  bestStreak: 16, doneToday: true,  recentDays: dotHistory(13) },
  { id: 'h-read',     userId: mockUser.id, name: 'Read · paper', tag: '20 pages · before bed', intent: "keep a mind that isn't a feed", color: 'indigo', supports: ['h-phonebed'], streakDays: 4, bestStreak: 22, doneToday: false, recentDays: dotHistory(19) },
  { id: 'h-water',    userId: mockUser.id, name: 'Water early', tag: 'before coffee',     intent: 'morning headaches',          color: 'sage',   supports: [],             streakDays: 21, bestStreak: 21, doneToday: true,  recentDays: dotHistory(23) },
  { id: 'h-phonebed', userId: mockUser.id, name: 'No phone in bed', tag: 'after 10pm', intent: 'fall asleep before midnight',   color: 'rose',   supports: [],             streakDays: 0,  bestStreak: 5,  doneToday: false, recentDays: dotHistory(5)  },
];

export const mockHabitsToday: HabitsTodayResponse = {
  habits: mockHabits,
  doneCount: mockHabits.filter(h => h.doneToday).length,
  totalCount: mockHabits.length,
  consistency30d: 0.67,
  longestActiveStreak: 21,
  suggestion: {
    id: 's-stretch',
    kind: 'new-habit',
    text: "Stretch · 5 min after coffee. You mentioned tight hips 4 times in the last 2 weeks.",
  } as IrisSuggestion,
};

// ─── Insights ───────────────────────────────────────────────────────────────

export const mockInsights: InsightSummary[] = [
  {
    id: 'i-body-words', kind: 'fusion', status: 'new',
    headline: { line1: 'Your body forgives you', line2: 'faster than', line3: 'you forgive yourself.' },
    summary: 'On 9 of the last 11 days you scored your day a 4–6 — while your overnight HRV climbed back to baseline within hours of the stressor ending.',
    accentColor: 'sage', featured: true,
    tags: ['fusion · air + journal', 'high confidence', '11 supporting nights'],
    confidence: 0.91, detectedAt: now(), seen: false,
  },
  {
    id: 'i-monday', kind: 'temporal', status: 'active',
    headline: { line1: 'You are', line2: '32% more anxious', line3: 'on Mondays.' },
    summary: 'Anxiety climbs 32% Monday mornings vs. other weekday mornings — concentrated 8–11 AM, secondary peak Sunday evenings.',
    accentColor: 'rose', featured: false,
    tags: ['temporal', 'air-corroborated', '11 supporting entries'],
    confidence: 0.84, detectedAt: daysAgo(3), seen: true,
  },
  {
    id: 'i-sleep-mood', kind: 'causal', status: 'active',
    headline: { line1: 'Below 6.5h sleep', line2: 'drops your mood', line3: '1.2 pts tomorrow.' },
    summary: 'Strong inverse correlation (r=−0.71) between deep-sleep minutes and the following day\'s self-reported mood — holds across 28 nights.',
    accentColor: 'indigo', featured: false,
    tags: ['causal · likely', '28 nights'],
    confidence: 0.78, detectedAt: daysAgo(12), seen: true,
  },
  {
    id: 'i-shoulders', kind: 'linguistic', status: 'active',
    headline: { line1: 'You describe', line2: 'relief in your', line3: 'shoulders.' },
    summary: 'And dread in your jaw. A body-vocabulary that\'s consistent across 17 entries — Iris can listen for the words as early signals.',
    accentColor: 'amber', featured: false,
    tags: ['linguistic', 'embodied'],
    confidence: 0.66, detectedAt: daysAgo(8), seen: true,
  },
];

export const mockInsightDetail = (id: string): InsightDetail | null => {
  const summary = mockInsights.find(i => i.id === id);
  if (!summary) return null;
  return {
    ...summary,
    irisRead: "This isn't denial — your body really has bounced back. It's that the story you tell about a hard day lasts longer than the hard day. That gap is workable.",
    evidence: [
      {
        kind: 'twin-series',
        label: '14 days · words vs. body',
        series: [
          { name: 'body (air)', color: 'sage', points: [
            { x: 'Tue 14', y: 65 }, { x: 'Wed 15', y: 58 }, { x: 'Thu 16', y: 70 },
            { x: 'Fri 17', y: 78 }, { x: 'Sat 18', y: 82 }, { x: 'Sun 19', y: 80 },
            { x: 'Mon 20', y: 55 }, { x: 'Tue 21', y: 62 }, { x: 'Wed 22', y: 71 },
            { x: 'Thu 23', y: 73 }, { x: 'Fri 24', y: 80 }, { x: 'Sat 25', y: 84 },
            { x: 'Sun 26', y: 78 }, { x: 'Tue 27', y: 72 },
          ]},
          { name: 'words (you)', color: 'amber', points: [
            { x: 'Tue 14', y: 50 }, { x: 'Wed 15', y: 40 }, { x: 'Thu 16', y: 60 },
            { x: 'Fri 17', y: 70 }, { x: 'Sat 18', y: 80 }, { x: 'Sun 19', y: 70 },
            { x: 'Mon 20', y: 30 }, { x: 'Tue 21', y: 40 }, { x: 'Wed 22', y: 60 },
            { x: 'Thu 23', y: 50 }, { x: 'Fri 24', y: 70 }, { x: 'Sat 25', y: 80 },
            { x: 'Sun 26', y: 70 }, { x: 'Tue 27', y: 40 },
          ]},
        ],
      },
      {
        kind: 'comparison', label: 'the shape of the gap',
        items: [
          { label: 'avg gap · last 14d', value: 28 },
          { label: 'how long words lag', value: 22, sub: 'hours' },
          { label: 'peak gap · monday', value: 42 },
        ],
      },
    ],
    pullQuotes: [
      { sourceDate: dateAgo(7),  text: "Couldn't get my breath until 10. The day felt like it started without me.", sourceKind: 'journal' },
      { sourceDate: dateAgo(4),  text: "Couldn't sleep. Mind on the design review.", sourceKind: 'journal' },
      { sourceDate: dateAgo(0),  text: "Honestly kind of fried.", sourceKind: 'chat' },
    ],
    related: [
      { id: 'i-monday',     label: 'Monday anxiety (32% higher)',    tag: 'temporal' },
      { id: 'i-sleep-mood', label: 'Sleep ↔ next-day mood',          tag: 'causal' },
      { id: 'i-shoulders',  label: 'Shoulder = relief, jaw = dread', tag: 'language' },
    ],
    suggestions: [
      { id: 's1', label: 'At 9 PM, Iris shows you today\'s HRV before you write', impact: 'meet the day with both stories' },
      { id: 's2', label: 'Mid-day glance: "you\'re at 68, words say 42"',        impact: 'gentle calibration in the moment' },
      { id: 's3', label: 'Sunday review reframes a hard week against body data', impact: 'shorten the story\'s shadow' },
      { id: 's4', label: 'Anchor phrase: "the body has already turned"',          impact: 'a sentence to hold on Monday morning' },
    ],
    methodology: 'Twin time-series: overnight HRV recovery from Fitbit Air vs. next-morning self-rated energy & mood. Required 14+ days of both signals.',
  };
};

// ─── Body ───────────────────────────────────────────────────────────────────

function mkSeries(n: number, base: number, amp: number, seed: number): number[] {
  let s = seed;
  return Array.from({ length: n }, (_, i) => {
    s = (s * 9301 + 49297) % 233280;
    return base + Math.sin(i / 2.3) * amp * 0.4 + ((s / 233280) - 0.5) * amp * 0.8;
  });
}

const hrv14    = mkSeries(14, 48, 12, 41);
const rhr14    = mkSeries(14, 58, 5,  73);
const brth14   = mkSeries(14, 14.6, 1.4, 19);
const temp14   = mkSeries(14, 0.0, 0.45, 29);
const readiness14 = mkSeries(14, 68, 14, 53).map(v => Math.max(20, Math.min(98, Math.round(v))));

export const mockBody: BodyOverviewResponse = {
  recent: Array.from({ length: 14 }, (_, i): BodyDay => ({
    date: dateAgo(13 - i),
    readiness: readiness14[i],
    hrvMs: Math.round(hrv14[i]),
    rhrBpm: Math.round(rhr14[i]),
    breathingRate: parseFloat(brth14[i].toFixed(1)),
    skinTempDeltaF: parseFloat(temp14[i].toFixed(2)),
    cardioLoad: [18, 22, 11, 16, 8, 28, 14, 19, 24, 12, 21, 17, 9, 14][i],
    sleep: i === 13 ? {
      startedAt: daysAgo(0),
      endedAt: now(),
      totalMinutes: 411,
      awakenings: 3,
      stages: [
        { stage: 'awake', startedAt: daysAgo(0), minutes: 23 },
        { stage: 'rem',   startedAt: daysAgo(0), minutes: 78 },
        { stage: 'light', startedAt: daysAgo(0), minutes: 188 },
        { stage: 'deep',  startedAt: daysAgo(0), minutes: 122 },
      ],
    } : undefined,
    rhythmFlags: { afib: false },
  })),
  rollups: {
    hrvBaselineMs: 47,
    rhrBaselineBpm: 58,
    avgReadiness14d: 67,
  },
  source: {
    kind: 'fitbit-air',
    label: 'Fitbit Air',
    connected: true,
    lastSyncedAt: now(),
    batteryPct: 71,
    daysBatteryLeft: 5,
  },
};

// ─── Journal ────────────────────────────────────────────────────────────────

export const mockJournal: JournalListResponse = {
  entries: [
    { id: 'j1', userId: mockUser.id, lines: ["The room felt fast. Joel pivoted twice.", "I noticed I was bracing my jaw the whole hour.", "Only caught it when it ached at 3."],
      mood: 5, tags: ['work','body','anxiety'], irisNote: "this is the 3rd time you've mentioned jaw tension in a meeting.",
      createdAt: daysAgo(1) },
    { id: 'j2', userId: mockUser.id, lines: ["Coffee on the porch.", "Read 14 pages without checking my phone.", "Felt like the kind of slow I used to know."],
      mood: 8, tags: ['rest','reading'], irisNote: "longest unbroken read window in 22 days.",
      createdAt: daysAgo(2) },
    { id: 'j3', userId: mockUser.id, lines: ["We talked about August and didn't decide anything.", "That was kind of the point.", "Foggy at the trailhead, sunny by the top."],
      mood: 7, tags: ['relationships','movement'], createdAt: daysAgo(3) },
    { id: 'j4', userId: mockUser.id, lines: ["Mind on the design review.", "Tried the breathing thing twice.", "The second time it actually worked, around 1."],
      mood: 4, tags: ['sleep','anxiety','work'], irisNote: "design review surfaced 9 days running.",
      createdAt: daysAgo(4) },
  ] as JournalEntry[],
  recurringPhrases: [
    { phrase: 'bracing my jaw',           count: 3 },
    { phrase: 'mind on the design review', count: 9 },
    { phrase: 'slow morning',              count: 4 },
    { phrase: "didn't decide anything",    count: 2 },
    { phrase: 'the kind of slow',          count: 2 },
  ],
};

// ─── Settings ───────────────────────────────────────────────────────────────

export const mockKnowsAboutYou: KnownFact[] = [
  { id: 'f1', fact: "I work in design. Lead level. Joel is my manager.",                      source: 'chat',     ageDays: 47, editable: true },
  { id: 'f2', fact: "I live in Oakland. My partner is M. We hike together.",                  source: 'journal',  ageDays: 43, editable: true },
  { id: 'f3', fact: "My standup is Tuesdays at 9. It often runs over.",                       source: 'pattern',  ageDays: 38, editable: true },
  { id: 'f4', fact: "Sleep below 6.5h makes my next-day mood drop ~1.2 points.",              source: 'derived',  ageDays: 21, editable: false },
  { id: 'f5', fact: "My HRV baseline is 47 ms. Below 40 — I feel it before I see it.",        source: 'air',      ageDays: 18, editable: false },
  { id: 'f6', fact: "I describe relief in my shoulders. I describe dread in my jaw.",         source: 'language', ageDays: 17, editable: true },
  { id: 'f7', fact: "My body recovers faster than my words admit (gap avg +28).",             source: 'fusion',   ageDays: 12, editable: false },
  { id: 'f8', fact: "Mom has an appointment coming up. I haven't called her in 9 days.",      source: 'chat',     ageDays: 5,  editable: true },
];

export const mockConnectors: DataConnector[] = [
  { id: 'fitbit-air',   name: 'Fitbit Air',     scopeDescription: 'paired apr 14 · 24/7 · 71% battery', state: 'connected', featured: true, lastSyncedAt: now() },
  { id: 'google-health',name: 'Google Health',  scopeDescription: 'cardio load, readiness, AFib watch', state: 'connected', lastSyncedAt: now() },
  { id: 'calendar',     name: 'Calendar',       scopeDescription: 'titles only · no body', state: 'connected', lastSyncedAt: now() },
  { id: 'spotify',      name: 'Spotify',        scopeDescription: 'listening mood (private)', state: 'connected', lastSyncedAt: now() },
  { id: 'photos',       name: 'Photos',         scopeDescription: 'scene + faces, on-device', state: 'paused' },
  { id: 'messages',     name: 'Messages',       scopeDescription: 'never. by design.', state: 'off' },
  { id: 'location',     name: 'Location',       scopeDescription: 'home/work radius only', state: 'off' },
];

// ─── Review ─────────────────────────────────────────────────────────────────

export const mockWeek: ReviewWeek = {
  weekStart: dateAgo(7), weekEnd: dateAgo(1),
  letter:
`Sam,

Your week started tight. By Friday's walk, your shoulders dropped a vocabulary level — you said "open" for the first time in nineteen days.

The thing you carried longest — the design review — is off your back. Notice what's landing in the space where it lived.

— Iris`,
  metrics: { moodAvg: 6.4, moodDelta: 0.6, sleepHoursAvg: 7.04, sleepDeltaMin: 12, habitsHit: 23, habitsTotal: 35, winsLogged: 4, hrvDeltaMs: 5 },
  days: [
    { date: dateAgo(7), shortName: 'mon', mood: 4.8, sleepHours: 5.9, word: 'tight'  },
    { date: dateAgo(6), shortName: 'tue', mood: 5.6, sleepHours: 6.4, word: 'fried'  },
    { date: dateAgo(5), shortName: 'wed', mood: 6.7, sleepHours: 7.4, word: 'steady' },
    { date: dateAgo(4), shortName: 'thu', mood: 5.2, sleepHours: 6.1, word: 'tired'  },
    { date: dateAgo(3), shortName: 'fri', mood: 7.4, sleepHours: 7.2, word: 'open'   },
    { date: dateAgo(2), shortName: 'sat', mood: 8.1, sleepHours: 8.1, word: 'slow'   },
    { date: dateAgo(1), shortName: 'sun', mood: 7.3, sleepHours: 7.4, word: 'quiet'  },
  ],
  themes: ['The body keeps the schedule.', 'Slow mornings undo something.', '"Open" is back in your vocabulary.'],
  winThatMattered: 'Shipped the design review.',
  strugglesLingering: 'Phone in bed — 5 of 7 nights.',
  lookahead: [
    { when: 'mon · 9 am', what: 'standup — pre-write sun 5pm?' },
    { when: 'sun · 9 pm', what: "Iris will ask: what's the dread?" },
  ],
};
