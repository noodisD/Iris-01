package com.iris.android

import com.iris.android.api.Coverage
import com.iris.android.api.DiscussionPreview
import com.iris.android.api.EvidenceRef
import com.iris.android.api.DayDifferenceDetail
import com.iris.android.api.PatternSummary
import com.iris.android.api.PatternVerdict
import com.iris.android.api.PatternsResponse
import com.iris.android.api.evidenceRoute
import com.iris.android.api.discoveryRange
import com.iris.android.api.json
import com.iris.android.api.nextPattern
import com.iris.android.api.patternRoute
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

class PatternsTest {
    private fun p(id: String, occasions: Int, verdict: String? = null, mixed: Int = 0) = PatternSummary(
        id = id, name = "Pattern $id", statement = "A source-backed situation",
        holdsWhen = emptyList(), notWhen = emptyList(), basis = null, evidence = null, source = null,
        occasions = occasions, tones = mapOf("worse" to occasions - mixed, "better" to 0, "mixed" to mixed),
        reviewed = 0, rejected = 0, labelledBy = emptyList(),
        verdict = verdict?.let { PatternVerdict(it) }, entryCount = occasions,
        recordedFrom = null, recordedTo = null, undatedAccountCount = occasions,
        examples = emptyList(), question = "What happened?", snapshot = "a".repeat(64),
        coverage = Coverage("all", "2026-09-29", null, null, occasions, occasions, occasions))

    @Test fun offersUnjudgedPatternsIncludingNoteOnly() {
        val patterns = listOf(p("a", 9, "rings_true"), p("b", 4),
            p("c", 6).copy(verdict = PatternVerdict(null, "I'm still considering this")), p("d", 0))
        assertEquals("c", nextPattern(patterns)?.id)
    }

    @Test fun offersNothingOnceEveryFoundPatternHasAVerdict() {
        assertNull(nextPattern(listOf(p("a", 3, "does_not"), p("b", 0))))
    }



    @Test fun decodesPeriodCoverageAndExactEvidenceWithoutInventedDefaults() {
        val body = """{"coverage":{"range":"30d","asOf":"2026-09-29","recordedFrom":"2026-09-18",
            "recordedTo":"2026-09-18","entryCount":1,"accountCount":1,"undatedAccountCount":0},
            "snapshot":"${"a".repeat(64)}",
            "patterns":[{"id":"x","name":"X","statement":"s","holdsWhen":[],"notWhen":[],
            "question":"q","basis":null,"evidence":"mixed","source":null,"occasions":1,
            "tones":{"better":1,"worse":0,"mixed":0},"reviewed":0,"rejected":0,"labelledBy":["m"],
            "entryCount":1,"recordedFrom":"2026-09-18","recordedTo":"2026-09-18","undatedAccountCount":0,
            "snapshot":"${"a".repeat(64)}",
            "coverage":{"range":"30d","asOf":"2026-09-29","recordedFrom":"2026-09-18",
            "recordedTo":"2026-09-18","entryCount":1,"accountCount":1,"undatedAccountCount":0},
            "examples":[{"id":"12","recordedOn":"2026-09-18","domain":null,"situation":"When I got home",
            "response":"I called her","outcome":"We talked","explanation":null,"citations":[
            {"entryId":"7","sourceType":"reflection","entryDate":"2026-09-18","text":"I called her"}],
            "suggestedTone":"better","ownerTone":"worse","tone":"worse","size":null,
            "labelledBy":"m","ownerVerdict":null,"verdictNote":null}],
            "verdict":{"verdict":null,"note":"Still thinking"}}]}"""
        val result = json.decodeFromString(PatternsResponse.serializer(), body)
        val decoded = result.patterns.single()
        assertEquals("30d", result.coverage.range)
        assertEquals("Still thinking", decoded.verdict?.note)
        assertNull(decoded.verdict?.verdict)
        assertEquals("2026-09-18", decoded.examples.single().recordedOn)
        assertEquals("I called her", decoded.examples.single().citations.single().text)
        assertEquals("better", decoded.examples.single().suggestedTone)
        assertEquals("worse", decoded.examples.single().tone)
        assertEquals(1, decoded.entryCount)
    }

    @Test fun rangeLinksRetainTheSelectedPeriodAndRejectUnknownInput() {
        assertEquals("patterns/x?range=90d", patternRoute("x", "90d"))
        assertThrows(IllegalArgumentException::class.java) { discoveryRange("nonsense") }
    }

    @Test fun decodesContributingCheckinsAndExclusionsFromDayEvidence() {
        val body = """{"difference":{"outcome":"energy","split":"office_home","sentence":"unused",
          "leftCount":5,"rightCount":5,"leftMean":2.0,"rightMean":8.0,"pValue":0.007,
          "verdict":null,"leftLabel":"office days","rightLabel":"home days","threshold":null,
          "coverage":{"range":"90d","asOf":"2026-09-29","recordedFrom":"2026-09-15",
            "recordedTo":"2026-09-24","measuredDays":12,"checkinDays":11,"overlappingDays":10},
          "snapshot":"${"b".repeat(64)}"},
          "leftDays":[{"day":"2026-09-24","value":2.0,"splitValue":"office","entryIds":["34","36"]}],
          "rightDays":[{"day":"2026-09-15","value":8.0,"splitValue":"home","entryIds":["29"]}],
          "excluded":{"missingScore":1,"missingMeasurement":1,"lowCoverage":2,
            "partialSteps":0,"medianTies":0}}"""
        val detail = json.decodeFromString(DayDifferenceDetail.serializer(), body)
        assertEquals(listOf("34", "36"), detail.leftDays.single().entryIds)
        assertEquals("home days", detail.difference.rightLabel)
        assertEquals(2, detail.excluded["lowCoverage"])
        assertEquals("90d", detail.difference.coverage.range)
    }

    @Test fun selectedEvidenceRouteCarriesOnlyTypedPointerAndCurrentPreviewCanReplaceSnapshot() {
        val ref = EvidenceRef.CoLabel("garden", "setback", "90d", "a".repeat(64))
        val route = evidenceRoute(ref)
        val decoded = java.net.URLDecoder.decode(route.substringAfter("evidence="), Charsets.UTF_8)
        assertEquals(ref, json.decodeFromString(EvidenceRef.serializer(), decoded))
        assertEquals("chat?evidence=", route.substringBefore("%7B"))
        val preview = json.decodeFromString(DiscussionPreview.serializer(), """{
            "ref":{"kind":"co_label","patternId":"garden","otherId":"setback","range":"90d",
              "snapshot":"${"b".repeat(64)}"},
            "title":"Garden and setback","question":"Why?","changed":true,
            "evidence":{"groups":{"betterWith":[],"worseWith":[]},"mixedExcluded":0}}""")
        assertEquals("b".repeat(64), preview.ref.snapshot)
        assertEquals(true, preview.changed)
        assertThrows(IllegalArgumentException::class.java) {
            evidenceRoute(EvidenceRef.Pattern("garden", "90d", "invalid"))
        }
    }

}
