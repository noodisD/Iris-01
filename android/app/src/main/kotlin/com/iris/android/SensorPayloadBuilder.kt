package com.iris.android

import java.time.Instant
import java.time.LocalDate

/**
 * Builds a PixelAdapter-shaped payload from buffered sensor data.
 *
 * Pure / JVM-testable: no Android APIs. Returns a plain Map that the
 * Android-side service layer (or the JVM-side IrisApiClient tests)
 * serialises to JSON. The contract between the phone and IRIS is the
 * shape — see tests/fixtures/pixel_export_minimal.json — not the
 * transport.
 */
class SensorPayloadBuilder(
    private val deviceName: String = "Pixel 10a",
) {
    data class LocationReading(
        val ts: Instant, val lat: Double, val lon: Double,
        val accuracyMeters: Int,
    )

    data class AppUsageReading(
        val ts: Instant, val packageName: String,
        val foregroundSeconds: Int,
    )

    data class StepsReading(val date: LocalDate, val count: Int)

    fun build(
        exportedAt: Instant = Instant.now(),
        location: List<LocationReading> = emptyList(),
        appUsage: List<AppUsageReading> = emptyList(),
        steps: List<StepsReading> = emptyList(),
    ): Map<String, Any?> = mapOf(
        "device" to deviceName,
        "exported_at" to exportedAt.toString(),
        "tiers" to mapOf(
            "location" to location.map { r ->
                mapOf(
                    "ts" to r.ts.toString(),
                    "lat" to r.lat,
                    "lon" to r.lon,
                    "accuracy_m" to r.accuracyMeters,
                )
            },
            "app_usage" to appUsage.map { r ->
                mapOf(
                    "ts" to r.ts.toString(),
                    "package" to r.packageName,
                    "foreground_seconds" to r.foregroundSeconds,
                )
            },
            "steps" to steps.map { r ->
                mapOf("date" to r.date.toString(), "count" to r.count)
            },
        ),
    )
}
