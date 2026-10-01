package com.iris.android

import com.iris.android.api.DayDifferenceDetail
import com.iris.android.api.DiscussionPreview
import com.iris.android.api.EvidenceRef
import com.iris.android.api.InsightDetail
import com.iris.android.api.PatternDetail
import com.iris.android.api.PatternsResponse
import com.iris.android.api.PersonalPattern
import com.iris.android.api.discoveryRange
import com.iris.android.api.evidenceRoute
import com.iris.android.api.insightRoute
import com.iris.android.api.json
import com.iris.android.api.nextPattern
import com.iris.android.api.patternRoute
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class PatternsTest {
    private val dynamic = "d_${"a".repeat(64)}"
    private val insight = "i_${"b".repeat(64)}"
    private val snapshot = "c".repeat(64)
    private val citation = """{"entryId":"17","sourceType":"reflection","entryDate":"2026-09-18","text":"I checked before answering"}"""
    private val status = """{"readerVersion":"r","discoveryVersion":"d","interpretationVersion":"i",
        "libraryVersion":"l","model":"worker","stage":"ready","eligibleEntries":2,"currentEntries":2,
        "unreadEntries":0,"pendingEntries":0,"failedEntries":0,"excludedEntries":0,"omittedAccounts":0,
        "omittedFields":0,"synthesisPending":false,"synthesisFailed":false,"lastCompletedAt":null,
        "estimate":{"readingRequests":0,"synthesisRequests":0,"tokensIn":0,"tokensOut":0,"costText":"$0",
        "approximate":true}}"""
    private val coverage = """{"range":"30d","asOf":"2026-10-01","recordedFrom":"2026-09-18",
        "recordedTo":"2026-09-24","entryCount":2,"accountCount":2,"undatedAccountCount":0}"""
    private val account = """{"id":"account-1","actor":"self","recordKind":"event","situation":"Someone waited",
        "response":"I checked before answering","demand":null,"information":null,"feeling":null,"concern":null,
        "immediateOutcome":null,"laterOutcome":null,"explanation":null,"selfReport":null,"domain":null,
        "recordedOn":"2026-09-18","citations":[$citation]}"""
    private val personal = """{"id":"$dynamic","title":"Checking capacity before an answer",
        "context":{"text":"Someone waited","refs":[{"accountId":"account-1","field":"situation","citationIndex":0}]},
        "response":{"text":"I checked before answering","refs":[{"accountId":"account-1","field":"response","citationIndex":0}]},
        "evidenceState":"emerging","ownerMeanings":[],"immediateReturn":null,"laterCost":null,
        "possibleMeaning":null,"alternative":null,"openQuestion":"What differed?","lensMatches":[],
        "exceptionGroupIds":[],"responseElsewhereGroupIds":[],"independentGroupCount":2,
        "accountCount":2,"entryCount":2,"recordedFrom":"2026-09-18","recordedTo":"2026-09-24",
        "undatedAccountCount":0,"exceptionCount":0,"unknownAccountCount":0,
        "example":{"accountId":"account-1","recordedOn":"2026-09-18","citation":$citation},
        "range":"30d","asOf":"2026-10-01","claimHash":"${"d".repeat(64)}","snapshot":"$snapshot",
        "feedback":{"verdict":null,"note":"Keep this exact note","updatedAt":"2026-10-01","needsReview":false}}"""
    private val membership = """{"dynamicId":"$dynamic","accountId":"account-1","groupId":"account-1",
        "role":"support","contextDecision":"present","responseDecision":"present","relationDecision":"linked",
        "refs":[],"ownerVerdict":"no","verdictNote":"This was a different choice","excluded":true}"""

    @Test fun decodesPersonalPatternAndExcludedAccountWithoutInventingAnOutcome() {
        val list = json.decodeFromString(PatternsResponse.serializer(),
            """{"patterns":[$personal],"coverage":$coverage,"status":$status,"snapshot":"$snapshot"}""")
        val pattern = list.patterns.single()
        assertEquals("Keep this exact note", pattern.feedback?.note)
        assertNull(pattern.immediateReturn)
        assertNull(pattern.laterCost)
        assertEquals("17", pattern.example?.citation?.entryId)
        assertEquals("30d", pattern.range)
        val detail = json.decodeFromString(PatternDetail.serializer(),
            """{"pattern":$personal,"accounts":{"account-1":$account},"memberships":{"$dynamic":[$membership]},
                "groups":{"$dynamic":[{"id":"account-1","accountIds":["account-1"],"role":"support",
                "independentlyCountable":false,"independenceUncertain":true}]},
                "lenses":[],"checks":{"checked":1,"unclear":0,"omittedAccounts":0,"omittedFields":0,
                "exceptionSearchComplete":true},"coverage":$coverage,"status":$status,"snapshot":"$snapshot"}""")
        assertTrue(detail.memberships.getValue(dynamic).single().excluded)
        assertEquals("This was a different choice", detail.memberships.getValue(dynamic).single().verdictNote)
        assertFalse(detail.groups.getValue(dynamic).single().independentlyCountable)
        assertTrue(detail.checks.exceptionSearchComplete)
        assertNull(detail.accounts.getValue("account-1").laterOutcome)
        assertEquals("17", detail.accounts.getValue("account-1").citations.single().entryId)
    }

    @Test fun unavailableLensLibraryDoesNotHideReadingStatus() {
        val reading = status.replace("\"libraryVersion\":\"l\"", "\"libraryVersion\":null")
            .replace("\"stage\":\"ready\"", "\"stage\":\"reading\"")
        val list = json.decodeFromString(PatternsResponse.serializer(),
            """{"patterns":[],"coverage":$coverage,"status":$reading,"snapshot":"$snapshot"}""")
        assertNull(list.status.libraryVersion)
        assertEquals("reading", list.status.stage)
    }

    @Test fun todayPreservesListOrderAndOffersNoteOnlyAndStaleOpinions() {
        val first = json.decodeFromString(PersonalPattern.serializer(), personal)
        val approved = first.copy(id = "approved", feedback = first.feedback?.copy(verdict = "rings_true"))
        val noteOnly = first.copy(id = "note")
        val stale = approved.copy(id = "stale", feedback = approved.feedback?.copy(needsReview = true))
        assertEquals("note", nextPattern(listOf(approved, noteOnly, stale))?.id)
        assertEquals("stale", nextPattern(listOf(approved, stale))?.id)
        assertNull(nextPattern(listOf(approved)))
    }

    @Test fun insightDetailSeparatesMembershipsOfTwoDifferentDynamics() {
        val second = "d_${"e".repeat(64)}"
        val hypothesis = """{"text":"Perhaps a stated concern mattered","premises":[{"text":"Someone waited",
            "refs":[{"accountId":"account-1","field":"situation","citationIndex":0}]}],
            "scopeGroupIds":["account-1"],"ownerReportIds":[]}"""
        val payload = """{"id":"$insight","kind":"shared_concern","dynamicIds":["$dynamic","$second"],
            "title":"Two responses and one concern","observation":{"text":"Someone waited","refs":[
            {"accountId":"account-1","field":"situation","citationIndex":0}]},"possibleMeaning":$hypothesis,
            "alternative":$hypothesis,"immediateReturn":null,"laterCost":null,"supportingGroups":["account-1"],
            "contraryGroups":[],"unknownAccountIds":[],"question":"What would distinguish these?",
            "range":"30d","asOf":"2026-10-01","claimHash":"${"f".repeat(64)}","snapshot":"$snapshot","feedback":null}"""
        val detail = json.decodeFromString(InsightDetail.serializer(),
            """{"insight":$payload,"accounts":{"account-1":$account},
                "memberships":{"$dynamic":[$membership],"$second":[${membership.replace(dynamic, second).replace("support", "exception")}]},
                "groups":{"$dynamic":[],"$second":[]},"coverage":$coverage,"status":$status,"snapshot":"$snapshot"}""")
        assertEquals("support", detail.memberships.getValue(dynamic).single().role)
        assertEquals("exception", detail.memberships.getValue(second).single().role)
        assertEquals("shared_concern", detail.insight.kind)
    }

    @Test fun typedDiscussionLinksRetainRangeAndRejectLegacyOrInvalidReferences() {
        assertEquals("patterns/${dynamic}?range=90d", patternRoute(dynamic, "90d"))
        assertEquals("insights/${insight}?range=30d", insightRoute(insight, "30d"))
        assertThrows(IllegalArgumentException::class.java) { discoveryRange("nonsense") }
        val ref = EvidenceRef.PersonalInsight(insight, "90d", snapshot)
        val decoded = java.net.URLDecoder.decode(evidenceRoute(ref).substringAfter("evidence="), Charsets.UTF_8)
        assertEquals(ref, json.decodeFromString(EvidenceRef.serializer(), decoded))
        val preview = json.decodeFromString(DiscussionPreview.serializer(), """{
            "ref":{"kind":"dynamic","dynamicId":"$dynamic","range":"90d","snapshot":"$snapshot"},
            "title":"Checking capacity","question":"What differed?","changed":true,"evidence":{}}""")
        assertTrue(preview.changed)
        assertEquals(dynamic, (preview.ref as EvidenceRef.Dynamic).dynamicId)
        assertThrows(IllegalArgumentException::class.java) {
            evidenceRoute(EvidenceRef.Dynamic(dynamic, "90d", "invalid"))
        }
        assertThrows(kotlinx.serialization.SerializationException::class.java) {
            json.decodeFromString(EvidenceRef.serializer(),
                """{"kind":"co_label","patternId":"garden","otherId":"work","range":"all","snapshot":"$snapshot"}""")
        }
    }

    @Test fun measuredDayEvidenceKeepsExactCheckinEntryIds() {
        val body = """{"difference":{"outcome":"energy","split":"office_home","sentence":"unused",
          "leftCount":5,"rightCount":5,"leftMean":2.0,"rightMean":8.0,"pValue":0.007,
          "verdict":null,"leftLabel":"office days","rightLabel":"home days","threshold":null,
          "coverage":{"range":"90d","asOf":"2026-09-29","recordedFrom":"2026-09-15",
            "recordedTo":"2026-09-24","measuredDays":12,"checkinDays":11,"overlappingDays":10},
          "snapshot":"${"b".repeat(64)}"},
          "leftDays":[{"day":"2026-09-24","value":2.0,"splitValue":"office","entryIds":["34","36"]}],
          "rightDays":[{"day":"2026-09-15","value":8.0,"splitValue":"home","entryIds":["29"]}],
          "excluded":{"lowCoverage":2}}"""
        val detail = json.decodeFromString(DayDifferenceDetail.serializer(), body)
        assertEquals(listOf("34", "36"), detail.leftDays.single().entryIds)
        assertEquals(2, detail.excluded["lowCoverage"])
    }
}
