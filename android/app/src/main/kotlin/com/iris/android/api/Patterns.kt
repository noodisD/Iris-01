package com.iris.android.api

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class PatternVerdict(val verdict: String?, val note: String? = null, val updatedAt: String? = null,
                          val needsReview: Boolean = false)

@Serializable
data class Coverage(val range: String, val asOf: String, val recordedFrom: String?,
                    val recordedTo: String?, val entryCount: Int, val accountCount: Int,
                    val undatedAccountCount: Int)

val DISCOVERY_RANGES = listOf("all", "30d", "90d")
fun discoveryRange(range: String): String = range.also { require(it in DISCOVERY_RANGES) }
private fun pathId(id: String) = java.net.URLEncoder.encode(id, "UTF-8").replace("+", "%20")
fun patternRoute(id: String, range: String) = "patterns/${pathId(id)}?range=${discoveryRange(range)}"
fun insightRoute(id: String, range: String) = "insights/${pathId(id)}?range=${discoveryRange(range)}"
fun patternDiscussionRoute(pattern: PersonalPattern, range: String) =
    evidenceRoute(EvidenceRef.Dynamic(pattern.id, discoveryRange(range), pattern.snapshot))
fun insightDiscussionRoute(insight: PersonalInsight, range: String) =
    evidenceRoute(EvidenceRef.PersonalInsight(insight.id, discoveryRange(range), insight.snapshot))
fun dayDiscussionRoute(d: DayDifference, range: String) =
    evidenceRoute(EvidenceRef.Day(d.outcome, d.split, discoveryRange(range), d.snapshot))

@Serializable data class QuoteRef(val accountId: String, val field: String, val citationIndex: Int)
@Serializable data class GroundedClause(val text: String, val refs: List<QuoteRef>)
@Serializable data class Hypothesis(val text: String, val premises: List<GroundedClause>,
                                    val scopeGroupIds: List<String>, val ownerReportIds: List<String>)
@Serializable data class SourceCitation(val entryId: String, val sourceType: String,
                                        val entryDate: String?, val text: String)
@Serializable data class PatternExample(val accountId: String, val recordedOn: String?, val citation: SourceCitation)
@Serializable data class LensMatch(val lensId: String, val qualifyingGroupIds: List<String>,
                                   val selfReportIds: List<String>, val requirementRefs: List<QuoteRef>,
                                   val excludedGroupIds: List<String>)
@Serializable data class PersonalPattern(
    val id: String, val title: String, val context: GroundedClause, val response: GroundedClause,
    val evidenceState: String, val ownerMeanings: List<GroundedClause>,
    val immediateReturn: GroundedClause?, val laterCost: GroundedClause?,
    val possibleMeaning: Hypothesis?, val alternative: Hypothesis?, val openQuestion: String,
    val lensMatches: List<LensMatch>, val exceptionGroupIds: List<String>,
    val responseElsewhereGroupIds: List<String>, val independentGroupCount: Int,
    val accountCount: Int, val entryCount: Int, val recordedFrom: String?, val recordedTo: String?,
    val undatedAccountCount: Int, val exceptionCount: Int, val unknownAccountCount: Int,
    val example: PatternExample?, val range: String, val asOf: String, val claimHash: String,
    val snapshot: String, val feedback: PatternVerdict?,
)
@Serializable data class SourceAccount(
    val id: String, val actor: String, val recordKind: String, val situation: String?,
    val response: String?, val demand: String?, val information: String?, val feeling: String?,
    val concern: String?, val immediateOutcome: String?, val laterOutcome: String?,
    val explanation: String?, val selfReport: String?, val domain: String?, val recordedOn: String?,
    val citations: List<SourceCitation>,
)
@Serializable data class PatternMembership(
    val dynamicId: String, val accountId: String, val groupId: String?, val role: String,
    val contextDecision: String, val responseDecision: String, val relationDecision: String,
    val refs: List<QuoteRef>, val ownerVerdict: String?, val verdictNote: String?, val excluded: Boolean,
)
@Serializable data class EventGroup(val id: String, val accountIds: List<String>, val role: String,
                                    val independentlyCountable: Boolean, val independenceUncertain: Boolean)
@Serializable data class ProcessLens(
    val id: String, val family: String, val name: String, val sequence: String,
    val possibleFunction: String, val immediateReturn: String, val possibleLaterCost: String,
    val requires: List<String>, val notWhen: String, val alternative: String,
    val question: String, val sourceIds: List<String>,
)
@Serializable data class DiscoveryEstimate(val readingRequests: Int, val synthesisRequests: Int,
    val tokensIn: Int, val tokensOut: Int, val costText: String, val approximate: Boolean)
@Serializable data class DiscoveryStatus(
    val readerVersion: String, val discoveryVersion: String, val interpretationVersion: String,
    val libraryVersion: String?, val model: String, val stage: String,
    val eligibleEntries: Int, val currentEntries: Int, val unreadEntries: Int,
    val pendingEntries: Int, val failedEntries: Int, val excludedEntries: Int,
    val omittedAccounts: Int, val omittedFields: Int, val synthesisPending: Boolean,
    val synthesisFailed: Boolean, val lastCompletedAt: String?, val estimate: DiscoveryEstimate,
)
@Serializable data class PatternsResponse(val patterns: List<PersonalPattern>, val coverage: Coverage,
                                          val status: DiscoveryStatus, val snapshot: String)
@Serializable data class PatternChecks(val checked: Int, val unclear: Int,
    val omittedAccounts: Int, val omittedFields: Int, val exceptionSearchComplete: Boolean)
@Serializable data class PatternDetail(val pattern: PersonalPattern,
    val accounts: Map<String, SourceAccount>, val memberships: Map<String, List<PatternMembership>>,
    val groups: Map<String, List<EventGroup>>, val lenses: List<ProcessLens>, val checks: PatternChecks,
    val coverage: Coverage, val status: DiscoveryStatus, val snapshot: String)

@Serializable data class PersonalInsight(
    val id: String, val kind: String, val dynamicIds: List<String>, val title: String,
    val observation: GroundedClause, val possibleMeaning: Hypothesis, val alternative: Hypothesis,
    val immediateReturn: GroundedClause?, val laterCost: GroundedClause?,
    val supportingGroups: List<String>, val contraryGroups: List<String>,
    val unknownAccountIds: List<String>, val question: String, val range: String, val asOf: String,
    val claimHash: String, val snapshot: String, val feedback: PatternVerdict?,
    val leftLabel: String? = null, val rightLabel: String? = null,
    val leftGroupIds: List<String>? = null, val rightGroupIds: List<String>? = null,
)
@Serializable data class InsightsResponse(val insights: List<PersonalInsight>, val coverage: Coverage,
                                          val status: DiscoveryStatus, val snapshot: String)
@Serializable data class InsightDetail(val insight: PersonalInsight,
    val accounts: Map<String, SourceAccount>, val memberships: Map<String, List<PatternMembership>>,
    val groups: Map<String, List<EventGroup>>, val coverage: Coverage,
    val status: DiscoveryStatus, val snapshot: String)
@Serializable data class Ok(val ok: Boolean)
@Serializable data class SavedFeedback(val feedback: PatternVerdict?, val snapshot: String)

val PATTERN_VERDICTS = listOf("rings_true" to "rings true", "does_not" to "doesn't ring true", "unsure" to "unsure")
val ACCOUNT_VERDICTS = listOf("yes" to "this fits", "no" to "not this", "unsure" to "unsure")

/** The server already orders the list; a note alone leaves the question unanswered. */
fun nextPattern(patterns: List<PersonalPattern>): PersonalPattern? =
    patterns.firstOrNull { it.feedback?.verdict == null || it.feedback.needsReview }

/** Measured phone/Timeline day groups remain independent of writing discovery. */
@Serializable data class DayDifference(
    val outcome: String, val split: String, val sentence: String, val leftCount: Int,
    val rightCount: Int, val leftMean: Double, val rightMean: Double, val pValue: Double,
    val verdict: PatternVerdict? = null, val leftLabel: String, val rightLabel: String,
    val threshold: Double?, val coverage: DayCoverage, val snapshot: String,
)
@Serializable data class DayCoverage(val range: String, val asOf: String, val recordedFrom: String,
    val recordedTo: String, val measuredDays: Int, val checkinDays: Int, val overlappingDays: Int)
@Serializable data class DayDiagnostics(val measuredDays: Int, val checkinDays: Int,
    val overlappingDays: Int, val eligibleComparisons: Int, val reason: String?)
@Serializable data class DayDifferencesResponse(val differences: List<DayDifference>, val diagnostics: DayDiagnostics)
@Serializable data class ContributingDay(val day: String, val value: Double,
    val splitValue: JsonElement, val entryIds: List<String>)
@Serializable data class DayDifferenceDetail(val difference: DayDifference,
    val leftDays: List<ContributingDay>, val rightDays: List<ContributingDay>, val excluded: Map<String, Int>)
