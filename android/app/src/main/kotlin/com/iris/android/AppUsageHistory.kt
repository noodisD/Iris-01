package com.iris.android

import android.content.Context
import android.content.Intent
import java.time.Instant
import org.json.JSONObject

/**
 * Sends the app-usage history Android still keeps: its detailed event log,
 * which reaches back about ten days. Owner-triggered, once: the live
 * collector skips time while collection was off, and this recovers it.
 */
internal object AppUsageHistory {
    /** How far back to ask. Android returns only what it still has. */
    const val DAYS = 10L

    fun window(now: Long): Pair<Long, Long> = (now - DAYS * 24 * 60 * 60_000) to now

    /** Reads, queues and asks the collector to deliver; returns how many intervals. */
    fun send(ctx: Context, now: Long = System.currentTimeMillis()): Int {
        val (from, until) = window(now)
        val readings = AppUsageReader.read(ctx, from, until)
        if (readings.isEmpty()) return 0
        val payload = SensorPayloadBuilder().build(exportedAt = Instant.ofEpochMilli(now), appUsage = readings)
        CollectorStore.get(ctx).enqueueHistory(JSONObject(payload).toString())
        ctx.startService(Intent(ctx, SensorCollectorService::class.java)
            .setAction(SensorCollectorService.ACTION_SYNC))
        return readings.size
    }
}
