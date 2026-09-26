package com.iris.android

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Process
import java.time.Instant

/** Splits foreground intervals at the acknowledged window boundaries. */
internal object AppUsageReader {
    fun hasPermission(ctx: Context): Boolean {
        val appOps = ctx.getSystemService(AppOpsManager::class.java)
        return appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), ctx.packageName
        ) == AppOpsManager.MODE_ALLOWED
    }

    fun read(ctx: Context, fromMillis: Long, untilMillis: Long): List<SensorPayloadBuilder.AppUsageReading> {
        check(hasPermission(ctx)) { "Usage access is not granted" }
        if (untilMillis <= fromMillis) return emptyList()
        val manager = ctx.getSystemService(UsageStatsManager::class.java)
        // Include the preceding activity transition: an app can remain in the foreground
        // when a sync window begins, without emitting another RESUMED event.
        val lookback = (fromMillis - 24L * 60 * 60_000).coerceAtLeast(0)
        val events = manager.queryEvents(lookback, untilMillis)
            ?: error("Android usage event history is unavailable")
        val event = UsageEvents.Event()
        val readings = mutableListOf<SensorPayloadBuilder.AppUsageReading>()
        val categories = mutableMapOf<String, String>()
        var foreground: String? = null
        var began = fromMillis
        // System UI "resumes" for the lock screen and always-on display while
        // the screen is off; nothing then is app use, so nothing is opened.
        var screenOn = true
        fun close(end: Long) {
            val pkg = foreground ?: return
            val start = began.coerceAtLeast(fromMillis)
            val seconds = ((end - start).coerceAtLeast(0) / 1_000).toInt()
            if (seconds > 0) readings.add(SensorPayloadBuilder.AppUsageReading(
                Instant.ofEpochMilli(start), pkg, seconds, categories.getOrPut(pkg) { categoryOf(ctx, pkg) }))
        }
        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            val timestamp = event.timeStamp
            if (timestamp > untilMillis) break
            when (event.eventType) {
                UsageEvents.Event.SCREEN_INTERACTIVE -> screenOn = true
                UsageEvents.Event.ACTIVITY_RESUMED -> {
                    if (foreground != null && timestamp >= fromMillis) close(timestamp)
                    if (screenOn && event.packageName !in NOT_APP_USE) {
                        foreground = event.packageName
                        began = timestamp.coerceAtLeast(fromMillis)
                    } else {
                        foreground = null
                    }
                }
                UsageEvents.Event.ACTIVITY_PAUSED,
                UsageEvents.Event.DEVICE_SHUTDOWN,
                UsageEvents.Event.SCREEN_NON_INTERACTIVE -> {
                    if (event.eventType != UsageEvents.Event.ACTIVITY_PAUSED) screenOn = false
                    if (foreground != null &&
                        (event.eventType != UsageEvents.Event.ACTIVITY_PAUSED ||
                            event.packageName == foreground)) {
                        if (timestamp >= fromMillis) close(timestamp)
                        foreground = null
                    }
                }
            }
        }
        close(untilMillis)
        return readings
    }

    /** The lock screen, shade and home screen: shown, but not an app in use. */
    val NOT_APP_USE = setOf("com.android.systemui", "com.google.android.apps.nexuslauncher", "com.android.launcher3")

    private fun categoryOf(ctx: Context, packageName: String): String {
        val info = try {
            ctx.packageManager.getApplicationInfo(packageName, 0)
        } catch (_: PackageManager.NameNotFoundException) {
            return "other"
        }
        return when (info.category) {
            ApplicationInfo.CATEGORY_GAME -> "game"
            ApplicationInfo.CATEGORY_AUDIO -> "audio"
            ApplicationInfo.CATEGORY_VIDEO -> "video"
            ApplicationInfo.CATEGORY_IMAGE -> "image"
            ApplicationInfo.CATEGORY_SOCIAL -> "social"
            ApplicationInfo.CATEGORY_NEWS -> "news"
            ApplicationInfo.CATEGORY_MAPS -> "maps"
            ApplicationInfo.CATEGORY_PRODUCTIVITY -> "productivity"
            else -> "other"
        }
    }
}
