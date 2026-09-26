package com.iris.android

import java.time.Instant
import java.time.LocalDate

/** Adapter-shaped JSON for durable, automatic Pixel and Health Connect delivery. */
class SensorPayloadBuilder(
    private val deviceName: String = "Pixel 10a",
) {
    companion object {
        const val HEALTH_CONNECT_DEVICE = "Health Connect"
        val TIER_ORDER = listOf("heart_rate", "sleep", "spo2")

        fun health(exportedAt: Instant, tiers: Map<String, List<Map<String, Any>>>): Map<String, Any?> =
            mapOf("device" to HEALTH_CONNECT_DEVICE, "exported_at" to exportedAt.toString(), "tiers" to tiers)

        fun chunkTiers(tiers: Map<String, List<Map<String, Any>>>, maxReadings: Int):
            List<Map<String, List<Map<String, Any>>>> {
            require(maxReadings > 0)
            val result = mutableListOf<Map<String, List<Map<String, Any>>>>()
            var current = TIER_ORDER.associateWith { mutableListOf<Map<String, Any>>() }
            var size = 0
            for (tier in TIER_ORDER) for (row in tiers[tier].orEmpty()) {
                if (size == maxReadings) {
                    result.add(current)
                    current = TIER_ORDER.associateWith { mutableListOf<Map<String, Any>>() }
                    size = 0
                }
                current.getValue(tier).add(row)
                size++
            }
            if (size > 0) result.add(current)
            return result
        }
    }
    data class LocationReading(
        val ts: Instant, val lat: Double, val lon: Double,
        val accuracyMeters: Int,
    )

    data class AppUsageReading(
        val ts: Instant, val packageName: String,
        val foregroundSeconds: Int,
        val category: String? = null,
    )

    data class StepsReading(val date: LocalDate, val count: Int, val observed: Boolean = false)

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
                    "category" to r.category,
                )
            },
            "steps" to steps.map { r ->
                if (r.observed) mapOf(
                    "date" to r.date.toString(), "count" to r.count,
                    "count_kind" to "observed",
                ) else mapOf("date" to r.date.toString(), "count" to r.count)
            },
        ),
    )
}
