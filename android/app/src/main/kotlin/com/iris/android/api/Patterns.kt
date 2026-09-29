package com.iris.android.api

import kotlinx.serialization.Serializable

// Discovery: general patterns from a library, and the occasions in the owner's
// writing that are instances of them. Wire names match GET /api/patterns.

@Serializable
data class PatternVerdict(val verdict: String?, val note: String? = null)

@Serializable
data class Coverage(
    val range: String,
    val asOf: String,
    val recordedFrom: String?,
    val recordedTo: String?,
    val entryCount: Int,
    val accountCount: Int,
    val undatedAccountCount: Int,
)

val DISCOVERY_RANGES = listOf("all", "30d", "90d")

fun discoveryRange(range: String): String {
    require(range in DISCOVERY_RANGES) { "Unknown reading range: $range" }
    return range
}

fun patternRoute(id: String, range: String) =
    "patterns/${java.net.URLEncoder.encode(id, Charsets.UTF_8).replace("+", "%20")}?range=${discoveryRange(range)}"
fun patternDiscussionRoute(pattern: PatternSummary, range: String): String =
    evidenceRoute(EvidenceRef.Pattern(pattern.id, discoveryRange(range), pattern.snapshot))

fun pairDiscussionRoute(pair: OutcomePair, range: String): String =
    evidenceRoute(EvidenceRef.Outcome(pair.patternId, discoveryRange(range), pair.snapshot))

fun coLabelDiscussionRoute(d: Difference, range: String): String =
    evidenceRoute(EvidenceRef.CoLabel(d.patternId, d.otherId, discoveryRange(range), d.snapshot))

fun dayDiscussionRoute(d: DayDifference, range: String): String =
    evidenceRoute(EvidenceRef.Day(d.outcome, d.split, discoveryRange(range), d.snapshot))


@Serializable
data class PatternSummary(
    val id: String,
    val name: String,
    val statement: String,
    val holdsWhen: List<String>,
    val notWhen: List<String>,
    val basis: String?,
    val evidence: String?,
    val source: String?,
    val occasions: Int,
    val tones: Map<String, Int>,
    val reviewed: Int,
    val rejected: Int,
    val labelledBy: List<String>,
    val verdict: PatternVerdict?,
    val entryCount: Int,
    val recordedFrom: String?,
    val recordedTo: String?,
    val undatedAccountCount: Int,
    val examples: List<Occasion>,
    val question: String,
    val snapshot: String,
    val coverage: Coverage,
)

@Serializable
data class PatternsResponse(val patterns: List<PatternSummary>, val coverage: Coverage, val snapshot: String)

@Serializable
data class PatternInfo(
    val id: String,
    val name: String,
    val statement: String,
    val holdsWhen: List<String>,
    val notWhen: List<String>,
    val question: String,
    val basis: String? = null,
    val evidence: String? = null,
    val source: String? = null,
)

@Serializable
data class OccasionCitation(
    val entryId: String,
    val sourceType: String,
    val entryDate: String?,
    val text: String,
)

@Serializable
data class Occasion(
    val id: String,
    val recordedOn: String?,
    val domain: String?,
    val situation: String,
    val response: String,
    val outcome: String?,
    val explanation: String?,
    val citations: List<OccasionCitation>,
    val suggestedTone: String,
    val ownerTone: String?,
    val tone: String,
    val size: String?,
    val labelledBy: String?,
    val ownerVerdict: String?,
    val verdictNote: String?,
)

@Serializable
data class DistinctivePattern(val patternId: String, val name: String, val better: Int, val worse: Int,
                              val betterTotal: Int, val worseTotal: Int,
                              val betterRate: Double, val worseRate: Double)

@Serializable
data class PatternDetail(
    val pattern: PatternInfo,
    val occasions: List<Occasion>,
    val distinctive: List<DistinctivePattern> = emptyList(),
    val verdict: PatternVerdict? = null,
    val coverage: Coverage,
    val snapshot: String,
)

@Serializable
data class Ok(val ok: Boolean)

/** Does the pattern ring true? The owner's answer, with its label. */
val PATTERN_VERDICTS = listOf("rings_true" to "rings true", "does_not" to "doesn't ring true", "unsure" to "unsure")

/** Is this occasion an instance of the pattern? */
val OCCASION_VERDICTS = listOf("yes" to "this one", "no" to "not this", "unsure" to "unsure")

/**
 * Today still offers the most frequent unjudged pattern. A note alone isn't a
 * judgment, so the owner can still answer the question later.
 */
fun nextPattern(patterns: List<PatternSummary>): PatternSummary? =
    patterns.filter { it.occasions > 0 && it.verdict?.verdict == null }
        .sortedWith(compareByDescending<PatternSummary> { it.occasions }.thenBy { it.name })
        .firstOrNull()


/**
 * An insight: a difference in outcome. Among a pattern's occasions, another
 * pattern that was there more often when it went one way than the other. Not a
 * cause; the owner judges it. Wire names match GET /api/differences.
 */
@Serializable
data class Difference(
    val patternId: String,
    val patternName: String,
    val otherId: String,
    val otherName: String,
    val worse: Int,
    val worseTotal: Int,
    val better: Int,
    val betterTotal: Int,
    val verdict: PatternVerdict? = null,
    val patternVerdict: PatternVerdict? = null,
    val betterRate: Double,
    val worseRate: Double,
    val rateGap: Double,
    val coverage: Coverage,
    val snapshot: String,
    val sampleLabel: String,
    val dismissed: Boolean,
)

@Serializable
data class OutcomePair(
    val kind: String,
    val patternId: String,
    val patternName: String,
    val question: String,
    val better: Occasion,
    val worse: Occasion,
    val betterTotal: Int,
    val worseTotal: Int,
    val mixedTotal: Int,
    val verdict: PatternVerdict?,
    val coverage: Coverage,
    val snapshot: String,
)

@Serializable
data class DifferenceDetail(
    val difference: Difference,
    val groups: Map<String, List<Occasion>>,
    val mixedExcluded: Int,
)

@Serializable
data class DifferencesResponse(val differences: List<Difference>, val reflections: List<OutcomePair>,
                               val coverage: Coverage, val snapshot: String)

/** Measured phone/Timeline day groups, compared without implying a cause. */
@Serializable
data class DayDifference(
    val outcome: String,
    val split: String,
    val sentence: String,
    val leftCount: Int,
    val rightCount: Int,
    val leftMean: Double,
    val rightMean: Double,
    val pValue: Double,
    val verdict: PatternVerdict? = null,
    val leftLabel: String,
    val rightLabel: String,
    val threshold: Double?,
    val coverage: DayCoverage,
    val snapshot: String,
)

@Serializable
data class DayCoverage(val range: String, val asOf: String, val recordedFrom: String,
                       val recordedTo: String, val measuredDays: Int, val checkinDays: Int,
                       val overlappingDays: Int)

@Serializable
data class DayDiagnostics(val measuredDays: Int, val checkinDays: Int, val overlappingDays: Int,
                          val eligibleComparisons: Int, val reason: String?)

@Serializable
data class DayDifferencesResponse(val differences: List<DayDifference>, val diagnostics: DayDiagnostics)

@Serializable
data class ContributingDay(val day: String, val value: Double,
                           val splitValue: kotlinx.serialization.json.JsonElement,
                           val entryIds: List<String>)

@Serializable
data class DayDifferenceDetail(val difference: DayDifference, val leftDays: List<ContributingDay>,
                               val rightDays: List<ContributingDay>,
                               val excluded: Map<String, Int>)
