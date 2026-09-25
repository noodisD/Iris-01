package com.iris.android.api

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

// These names are the wire names used by the web API, including the sensor API's snake_case.
@Serializable
data class User(
    val id: String,
    val name: String,
    val createdAt: String,
    val dayInJourney: Int,
    val timezone: String,
    val preferences: UserPreferences,
)

@Serializable
data class UserPreferences(
    val tone: String,
    val density: String,
    val dailyCheckinTime: String? = null,
    val weeklyReviewTime: String? = null,
    val maxNudgesPerDay: Int,
    val threadsListenedFor: List<String>,
)

@Serializable
data class ChatMessage(
    val id: String,
    val conversationId: String,
    val role: String,
    val text: String,
    val createdAt: String,
    val streaming: Boolean? = null,
)

@Serializable
data class Conversation(
    val id: String,
    val userId: String,
    val startedAt: String,
    val lastMessageAt: String,
    val messageCount: Int,
)

@Serializable
data class ChatStreamEvent(
    val text: String? = null,
    val done: Boolean? = null,
    val messageId: String? = null,
    val error: String? = null,
    val saved: Boolean? = null,
)

@Serializable
data class JournalEntry(
    val id: String,
    val userId: String,
    val lines: List<String>,
    val energy: Int? = null,
    val tags: List<String>? = null,
    val irisNote: String? = null,
    val occurredOn: String? = null,
    val importedAt: String? = null,
    val createdAt: String? = null,
    val audioUrl: String? = null,
)

@Serializable
data class JournalListResponse(
    val entries: List<JournalEntry>,
    val nextCursor: String? = null,
    val recurringPhrases: List<RecurringPhrase>? = null,
)

@Serializable
data class RecurringPhrase(val phrase: String, val count: Int)

@Serializable
data class Habit(
    val id: String,
    val userId: String,
    val name: String,
    val tag: String,
    val intent: String? = null,
    val color: String,
    val streakDays: Int,
    val bestStreak: Int,
    val doneToday: Boolean,
    val recentDays: List<Int>,
)

@Serializable
data class HabitsTodayResponse(
    val habits: List<Habit>,
    val doneCount: Int,
    val totalCount: Int,
    val consistency30d: Double,
    val longestActiveStreak: Int,
    val suggestion: IrisSuggestion? = null,
)

@Serializable
data class IrisSuggestion(
    val id: String,
    val kind: String,
    val text: String,
    val payload: Map<String, JsonElement>? = null,
)

@Serializable
data class HabitToggleRequest(
    val habitId: String,
    val done: Boolean,
    val date: String? = null,
)

@Serializable
data class DiscoveryRun(
    val status: String,
    val startedAt: String,
    val finishedAt: String? = null,
    val entriesRead: Int,
    val passesPlanned: Int,
    val passesCompleted: Int,
    val rawFindings: Int,
    val staged: Int,
    val dropped: DiscoveryDropped,
    val dropsRecorded: Boolean,
)

@Serializable
data class DiscoveryDropped(
    val mergedAway: Int,
    val unchecked: Int,
    val incomplete: Int,
    val denied: Int,
    val tooFewSupporting: Int,
    val alreadyDecided: Int,
    val notEmbedded: Int,
)

@Serializable
data class ConstructCandidate(
    val id: String,
    val claim: String,
    val summary: String,
    val origin: String,
    val claimKind: String? = null,
    val spanStart: String? = null,
    val spanEnd: String? = null,
    val quotes: List<ConstructQuote>,
)

@Serializable
data class ConstructQuote(
    val text: String,
    val entryId: String? = null,
    val sourceType: String,
    val citable: Boolean,
)

@Serializable
data class ConstructCandidatesResponse(val constructs: List<ConstructCandidate>)

@Serializable
data class DiscoveryRunResponse(val run: DiscoveryRun? = null)

@Serializable
data class ConstructConfirmResponse(val occurrences: Int)

@Serializable
data class ConstructRejectResponse(val status: String)

@Serializable
data class KnownFact(
    val id: String,
    val fact: String,
    val source: String,
    val ageDays: Int,
    val editable: Boolean,
)

@Serializable
data class AnalysisPreferences(
    val minConfidence: String,
    val maxItems: Int,
    val enabledEngines: List<String>? = null,
    val availableEngines: List<String>,
)

@Serializable
data class ImportAdapter(val name: String, val label: String, val description: String)

@Serializable
data class ImportBatch(
    val id: String,
    val kind: String,
    val adapter: String? = null,
    val detected: List<DetectedImportAdapter>,
    val originalFilename: String? = null,
    val status: String,
    val error: String? = null,
    val entryCount: Int,
    val committedCount: Int,
    val createdAt: String,
    val counts: ImportCounts,
)

@Serializable
data class DetectedImportAdapter(val adapter: String, val label: String, val score: Double)

@Serializable
data class ImportCounts(
    val total: Int,
    val staged: Int,
    val excluded: Int,
    val duplicate: Int,
    val imported: Int,
    val failed: Int,
    val needsDate: Int,
    val awaitingTranscript: Int,
    val earliest: String? = null,
    val latest: String? = null,
)

@Serializable
data class ImportEntry(
    val id: String,
    val sourceName: String? = null,
    val title: String? = null,
    val excerpt: String,
    val occurredOn: String? = null,
    val dateSource: String? = null,
    val dateConfidence: String,
    val dateUnknownAccepted: Boolean,
    val fileModifiedOn: String? = null,
    val status: String,
    val warnings: List<String>,
    val hasAudio: Boolean,
    val error: String? = null,
)

@Serializable
data class ImportEntriesResponse(val entries: List<ImportEntry>)

@Serializable
data class ImportBulkUpdateResponse(val updated: Int)

@Serializable
data class RecordingUploadResponse(
    val batchId: String,
    val entryId: String,
    val durationSeconds: Double? = null,
)

@Serializable
data class CommitResult(
    val committed: Int,
    val duplicates: Int,
    val failed: Int,
    val excluded: Int,
)

@Serializable
data class ReviewWeek(
    val weekStart: String,
    val weekEnd: String,
    val letter: String,
    val metrics: ReviewMetrics,
    val days: List<ReviewDay>,
    val themes: List<String>,
    val lookahead: List<ReviewLookahead>,
)

@Serializable
data class ReviewMetrics(
    val energyAvg: Double? = null,
    val energyDelta: Double? = null,
    val habitsHit: Int,
    val habitsTotal: Int,
)

@Serializable
data class ReviewDay(
    val date: String,
    val shortName: String,
    val energy: Int? = null,
    val word: String,
    val headline: String? = null,
)

@Serializable
data class ReviewLookahead(val `when`: String, val what: String)

@Serializable
data class OnboardingState(val step: String)

@Serializable
data class SensorObservation(
    val source_type: String,
    val occurred_at: String? = null,
    val value_num: Double? = null,
    val value_text: String? = null,
    val lat: Double? = null,
    val lon: Double? = null,
    val payload_hash: String,
    val origin_package: String? = null,
)

@Serializable
data class SensorBatch(
    val id: Long,
    val source: String,
    val received_at: String,
    val review_day: String? = null,
    val last_delivery_at: String? = null,
    val status: String,
    val observation_count: Int,
    val dropped_count: Int,
    val clock_skew_seconds: Double? = null,
    val parsed_payload: SensorParsedPayload? = null,
    val theme_links: Map<String, Long?>,
)

@Serializable
data class SensorParsedPayload(
    val device: String? = null,
    val exported_at: String? = null,
    val observations: List<SensorObservation>,
)

@Serializable
data class MobileConnection(
    val lan_url: String? = null,
    val public_key_sha256: String? = null,
    val listener: String,
    val listener_error: String? = null,
    val paired: Boolean,
    val paired_at: String? = null,
    val last_seen_at: String? = null,
    val last_intake_at: String? = null,
    val last_rejection: MobileRejection? = null,
    val pending_batches: Int,
)

@Serializable
data class MobileRejection(val at: String, val status: Int, val detail: String)

@Serializable
data class ApiError(val code: String, val message: String, val fields: Map<String, String>? = null)
