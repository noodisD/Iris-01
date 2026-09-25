package com.iris.android.lock

internal class AppLockPolicy(private val relockAfterMs: Long) {
    private var unlocked = false
    private var backgroundedAt: Long? = null

    /** onStart: true when the UI must show the lock screen. */
    fun onForeground(nowMs: Long): Boolean {
        val away = backgroundedAt?.let { nowMs - it }
        backgroundedAt = null
        if (away != null && away >= relockAfterMs) unlocked = false
        return !unlocked
    }

    fun onBackground(nowMs: Long) {
        if (unlocked) backgroundedAt = nowMs
    }

    fun onUnlocked() {
        unlocked = true
    }
}

internal val AppLock = AppLockPolicy(relockAfterMs = 5 * 60_000L)
