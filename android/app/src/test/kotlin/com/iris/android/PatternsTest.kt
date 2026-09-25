package com.iris.android

import com.iris.android.api.PatternSummary
import com.iris.android.api.PatternVerdict
import com.iris.android.api.PatternsResponse
import com.iris.android.api.byOccasions
import com.iris.android.api.json
import com.iris.android.api.nextPattern
import com.iris.android.api.toneCounts
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PatternsTest {
    private fun p(id: String, occasions: Int, verdict: String? = null, mixed: Int = 0) = PatternSummary(
        id = id, name = "Pattern $id", statement = "", occasions = occasions,
        tones = mapOf("worse" to occasions - mixed, "better" to 0, "mixed" to mixed),
        verdict = verdict?.let { PatternVerdict(it) })

    @Test fun offersTheMostFrequentPatternStillWithoutAVerdict() {
        val patterns = listOf(p("a", 9, "rings_true"), p("b", 4), p("c", 6), p("d", 0))
        assertEquals("c", nextPattern(patterns)?.id)
    }

    @Test fun offersNothingOnceEveryFoundPatternHasAVerdict() {
        assertNull(nextPattern(listOf(p("a", 3, "does_not"), p("b", 0))))
    }

    @Test fun listsByOccasionsThenName() {
        assertEquals(listOf("b", "c", "a"), byOccasions(listOf(p("a", 1), p("c", 5), p("b", 5))).map { it.id })
    }

    @Test fun countsTonesAndMentionsMixedOnlyWhenPresent() {
        assertEquals("none found", toneCounts(p("a", 0)))
        assertEquals("4 worse · 0 better", toneCounts(p("a", 4)))
        assertEquals("3 worse · 0 better · 1 mixed", toneCounts(p("a", 4, mixed = 1)))
    }

    @Test fun decodesTheServersListShape() {
        val body = """{"patterns":[{"id":"x","name":"X","statement":"s","holdsWhen":[],"notWhen":[],
            "question":"q","basis":null,"evidence":"mixed","source":null,"occasions":2,
            "tones":{"better":1,"worse":1,"mixed":0},"reviewed":0,"rejected":0,"labelledBy":["m"],
            "verdict":{"verdict":"unsure","note":null}}]}"""
        val decoded = json.decodeFromString(PatternsResponse.serializer(), body).patterns.single()
        assertEquals("unsure", decoded.verdict?.verdict)
        assertEquals(1, decoded.tones["better"])
    }
}
