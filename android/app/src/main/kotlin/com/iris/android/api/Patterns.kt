package com.iris.android.api

import kotlinx.serialization.Serializable

// Discovery: general patterns from a library, and the occasions in the owner's
// writing that are instances of them. Wire names match GET /api/patterns.

@Serializable
data class PatternVerdict(val verdict: String, val note: String? = null)

@Serializable
data class PatternSummary(
    val id: String,
    val name: String,
    val statement: String,
    val evidence: String? = null,
    /** Occasions, not counting any the owner said are not this pattern. */
    val occasions: Int,
    val tones: Map<String, Int> = emptyMap(),
    val verdict: PatternVerdict? = null,
)

@Serializable
data class PatternsResponse(val patterns: List<PatternSummary>)

@Serializable
data class PatternInfo(
    val id: String,
    val name: String,
    val statement: String,
    val basis: String? = null,
    val evidence: String? = null,
    val source: String? = null,
)

@Serializable
data class OccasionCitation(
    val entryId: String,
    val sourceType: String,
    val entryDate: String? = null,
    val text: String = "",
)

@Serializable
data class Occasion(
    val id: String,
    val occurredOn: String? = null,
    val situation: String,
    val response: String,
    val outcome: String? = null,
    val citations: List<OccasionCitation> = emptyList(),
    /** How it turned out, as the labelling read it: better, worse or mixed. */
    val tone: String,
    val labelledBy: String? = null,
    val ownerVerdict: String? = null,
    val verdictNote: String? = null,
)

@Serializable
data class DistinctivePattern(val patternId: String, val name: String, val better: Int, val worse: Int)

@Serializable
data class PatternDetail(
    val pattern: PatternInfo,
    val occasions: List<Occasion>,
    val distinctive: List<DistinctivePattern> = emptyList(),
    val verdict: PatternVerdict? = null,
)

@Serializable
data class Ok(val ok: Boolean)

/** Does the pattern ring true? The owner's answer, with its label. */
val PATTERN_VERDICTS = listOf("rings_true" to "rings true", "does_not" to "doesn't ring true", "unsure" to "unsure")

/** Is this occasion an instance of the pattern? */
val OCCASION_VERDICTS = listOf("yes" to "this one", "no" to "not this", "unsure" to "unsure")

/**
 * The pattern most worth a look: found on the most occasions and still without
 * the owner's verdict. Offered as a question, because whether it holds is theirs
 * to say.
 */
fun nextPattern(patterns: List<PatternSummary>): PatternSummary? =
    patterns.filter { it.occasions > 0 && it.verdict == null }
        .sortedWith(compareByDescending<PatternSummary> { it.occasions }.thenBy { it.name })
        .firstOrNull()

/** The list: patterns found in the owner's writing, most occasions first, then by name. */
fun byOccasions(patterns: List<PatternSummary>): List<PatternSummary> =
    patterns.filter { it.occasions > 0 }
        .sortedWith(compareByDescending<PatternSummary> { it.occasions }.thenBy { it.name })

/** "3 worse · 5 better", with mixed only when there are any. */
fun toneCounts(p: PatternSummary): String {
    if (p.occasions == 0) return "none found"
    val parts = mutableListOf("${p.tones["worse"] ?: 0} worse", "${p.tones["better"] ?: 0} better")
    val mixed = p.tones["mixed"] ?: 0
    if (mixed > 0) parts += "$mixed mixed"
    return parts.joinToString(" · ")
}

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
)

@Serializable
data class DifferencesResponse(val differences: List<Difference>)

/** The difference as one sentence, both sides counted. */
fun differenceSentence(d: Difference): String =
    "When ${d.patternName.lowercase()} came up, ${d.otherName.lowercase()} was there " +
        "${d.worse} of ${d.worseTotal} times it went worse, and ${d.better} of ${d.betterTotal} times it went better."

/** Those still waiting for the owner's verdict first, each group in server order. */
fun awaitingFirst(differences: List<Difference>): List<Difference> =
    differences.filter { it.verdict == null } + differences.filter { it.verdict != null }
