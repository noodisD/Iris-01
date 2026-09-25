package com.iris.android

import com.iris.android.api.Difference
import com.iris.android.api.PatternSummary
import com.iris.android.api.PatternVerdict
import com.iris.android.api.PatternsResponse
import com.iris.android.api.awaitingFirst
import com.iris.android.api.byOccasions
import com.iris.android.api.differenceSentence
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

    @Test fun listsFoundPatternsByOccasionsThenName() {
        assertEquals(listOf("b", "c", "a"), byOccasions(listOf(p("a", 1), p("c", 5), p("b", 5), p("z", 0))).map { it.id })
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

    private fun d(p: String, o: String, verdict: String? = null) = Difference(
        patternId = p, patternName = "Pattern $p", otherId = o, otherName = "Pattern $o",
        worse = 5, worseTotal = 6, better = 1, betterTotal = 7, verdict = verdict?.let { PatternVerdict(it) })

    @Test fun readsADifferenceAsASentenceWithBothSidesCounted() {
        assertEquals("When pattern a came up, pattern b was there 5 of 6 times it went worse, " +
            "and 1 of 7 times it went better.", differenceSentence(d("a", "b")))
    }

    @Test fun putsTheOnesWaitingForAVerdictFirst() {
        val ordered = awaitingFirst(listOf(d("a", "b", "rings_true"), d("c", "d"), d("e", "f", "unsure"), d("g", "h")))
        assertEquals(listOf("c", "g", "a", "e"), ordered.map { it.patternId })
    }
}
