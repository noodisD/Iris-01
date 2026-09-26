package com.iris.android

import org.junit.Assert.assertEquals
import org.junit.Test

class AppUsageHistoryTest {
    @Test fun asksForTenDaysEndingNow() {
        val now = 1_800_000_000_000L
        val (from, until) = AppUsageHistory.window(now)
        assertEquals(now, until)
        assertEquals(10L * 24 * 60 * 60_000, until - from)
    }
}
