package com.iris.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SensorPayloadBuilderTest {
    @Test fun splitsDenseHealthConnectSamplesWithoutChangingOrder() {
        val tiers = mapOf(
            "heart_rate" to (0 until 4_500).map { mapOf<String, Any>("record_key" to "h$it") },
            "sleep" to (0 until 3).map { mapOf<String, Any>("record_key" to "s$it") },
            "spo2" to (0 until 2).map { mapOf<String, Any>("record_key" to "o$it") },
        )
        val chunks = SensorPayloadBuilder.chunkTiers(tiers, 2_000)
        assertEquals(listOf(2_000, 2_000, 505), chunks.map { chunk -> chunk.values.sumOf { it.size } })
        assertTrue(chunks.all { it.keys == SensorPayloadBuilder.TIER_ORDER.toSet() })
        val expected = SensorPayloadBuilder.TIER_ORDER.flatMap { tier ->
            tiers.getValue(tier).map { it.getValue("record_key") }
        }
        val actual = chunks.flatMap { chunk ->
            SensorPayloadBuilder.TIER_ORDER.flatMap { tier ->
                chunk.getValue(tier).map { it.getValue("record_key") }
            }
        }
        assertEquals(expected, actual)
        assertTrue(SensorPayloadBuilder.chunkTiers(emptyMap(), 2_000).isEmpty())
    }

    @Test fun healthPayloadIdentifiesHealthConnectRatherThanTheWritingApp() {
        val tiers = mapOf(
            "heart_rate" to listOf(mapOf<String, Any>(
                "ts" to "2026-01-01T12:00:00Z", "bpm" to 74,
                "origin_package" to "com.google.android.apps.fitness",
            )),
            "sleep" to emptyList(), "spo2" to emptyList(),
        )
        val exportedAt = java.time.Instant.parse("2026-01-01T12:10:00Z")
        val payload = SensorPayloadBuilder.health(exportedAt, tiers)
        assertEquals("Health Connect", payload["device"])
    }
}
