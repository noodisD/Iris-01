package com.iris.android

import android.content.Context
import java.time.Instant

/** Durable transport and collection status, visible when the service is stopped. */
object SyncState {
    enum class Problem { WAITING, UNREACHABLE, BLOCKED, COLLECTION }

    data class Snapshot(
        val lastAttempt: Instant?,
        val lastSentPixel: Instant?,
        val lastSentHealth: Instant?,
        val problem: Problem?,
        val message: String?,
        val unreachableStreak: Int,
    )

    private const val PREFS = "iris_sync_status"
    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private fun instant(raw: String?) = raw?.let { runCatching { Instant.parse(it) }.getOrNull() }

    fun read(ctx: Context): Snapshot {
        val p = prefs(ctx)
        return Snapshot(
            instant(p.getString("last_attempt", null)),
            instant(p.getString("last_sent_pixel", null)),
            instant(p.getString("last_sent_health", null)),
            p.getString("problem", null)?.let { runCatching { Problem.valueOf(it) }.getOrNull() },
            p.getString("message", null),
            p.getInt("unreachable_streak", 0),
        )
    }

    fun recordAttempt(ctx: Context, at: Instant, sentPixel: Boolean, sentHealth: Boolean,
                      problem: Problem?, message: String?) {
        val old = prefs(ctx)
        val change = old.edit()
            .putString("last_attempt", at.toString())
            .putInt("unreachable_streak", if (problem == Problem.UNREACHABLE)
                old.getInt("unreachable_streak", 0) + 1 else 0)
        if (sentPixel) change.putString("last_sent_pixel", at.toString())
        if (sentHealth) change.putString("last_sent_health", at.toString())
        if (problem == null) change.remove("problem").remove("message")
        else change.putString("problem", problem.name).putString("message", message)
        check(change.commit()) { "Could not persist sensor sync status" }
    }

    fun recordProblem(ctx: Context, problem: Problem, message: String) {
        check(prefs(ctx).edit().putString("problem", problem.name)
            .putString("message", message)
            .putInt("unreachable_streak", 0)
            .commit()) { "Could not persist sensor sync problem" }
    }
}
