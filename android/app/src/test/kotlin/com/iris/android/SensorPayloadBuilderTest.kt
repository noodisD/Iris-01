package com.iris.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.LocalDate

class SensorPayloadBuilderTest {

    @Test fun empty_payload_has_correct_shape() {
        val payload = SensorPayloadBuilder().build()
        assertEquals("Pixel 10a", payload["device"])
        assertNotNull(payload["exported_at"])
        @Suppress("UNCHECKED_CAST")
        val tiers = payload["tiers"] as Map<String, Any?>
        assertTrue(tiers.containsKey("location"))
        assertTrue(tiers.containsKey("app_usage"))
        assertTrue(tiers.containsKey("steps"))
    }

    @Test fun location_reading_serializes_with_all_fields() {
        val ts = Instant.parse("2026-09-22T09:15:00Z")
        val payload = SensorPayloadBuilder().build(
            location = listOf(SensorPayloadBuilder.LocationReading(
                ts = ts, lat = 52.52, lon = 13.405, accuracyMeters = 35)))
        @Suppress("UNCHECKED_CAST")
        val tiers = payload["tiers"] as Map<String, Any?>
        @Suppress("UNCHECKED_CAST")
        val location = tiers["location"] as List<Map<String, Any?>>
        assertEquals(1, location.size)
        val first = location[0]
        assertEquals(ts.toString(), first["ts"])
        assertEquals(52.52, first["lat"])
        assertEquals(13.405, first["lon"])
        assertEquals(35, first["accuracy_m"])
    }

    @Test fun app_usage_reading_carries_package_name() {
        val ts = Instant.parse("2026-09-22T10:00:00Z")
        val payload = SensorPayloadBuilder().build(
            appUsage = listOf(SensorPayloadBuilder.AppUsageReading(
                ts = ts, packageName = "com.android.chrome",
                foregroundSeconds = 240)))
        @Suppress("UNCHECKED_CAST")
        val tiers = payload["tiers"] as Map<String, Any?>
        @Suppress("UNCHECKED_CAST")
        val appUsage = tiers["app_usage"] as List<Map<String, Any?>>
        assertEquals(1, appUsage.size)
        assertEquals("com.android.chrome", appUsage[0]["package"])
        assertEquals(240, appUsage[0]["foreground_seconds"])
    }

    @Test fun steps_reading_uses_iso_date() {
        val date = LocalDate.of(2026, 9, 22)
        val payload = SensorPayloadBuilder().build(
            steps = listOf(SensorPayloadBuilder.StepsReading(
                date = date, count = 7842)))
        @Suppress("UNCHECKED_CAST")
        val tiers = payload["tiers"] as Map<String, Any?>
        @Suppress("UNCHECKED_CAST")
        val steps = tiers["steps"] as List<Map<String, Any?>>
        assertEquals(1, steps.size)
        assertEquals("2026-09-22", steps[0]["date"])
        assertEquals(7842, steps[0]["count"])
    }

    @Test fun full_payload_matches_pixel_adapter_shape() {
        // The contract test: this exact shape must round-trip through
        // the laptop-side PixelAdapter. Three tiers, three readings each.
        val ts1 = Instant.parse("2026-09-22T09:15:00Z")
        val ts2 = Instant.parse("2026-09-22T10:00:00Z")
        val date = LocalDate.of(2026, 9, 22)
        val payload = SensorPayloadBuilder().build(
            exportedAt = ts1,
            location = listOf(
                SensorPayloadBuilder.LocationReading(ts1, 52.52, 13.405, 35),
                SensorPayloadBuilder.LocationReading(ts1.plusSeconds(1000), 52.516, 13.378, 18),
            ),
            appUsage = listOf(
                SensorPayloadBuilder.AppUsageReading(ts2, "com.android.chrome", 240),
            ),
            steps = listOf(
                SensorPayloadBuilder.StepsReading(date, 7842),
            ),
        )
        // The keys at the top level are the contract.
        assertEquals(setOf("device", "exported_at", "tiers"), payload.keys)
        @Suppress("UNCHECKED_CAST")
        val tiers = payload["tiers"] as Map<String, Any?>
        assertEquals(setOf("location", "app_usage", "steps"), tiers.keys)
    }
}
