package com.iris.android.ui.habits

import com.iris.android.api.Habit
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class HabitDaysTest {
    private fun habit(status: List<String>, notes: List<Boolean> = emptyList(), start: String? = null) = Habit(
        id = "1", userId = "1", name = "Invented habit", tag = "", color = "sage", streakDays = 0, bestStreak = 0,
        doneToday = false, recentDays = status.map { if (it == "done") 1 else 0 }, recentStatus = status,
        recentNotes = notes, recentStart = start)

    @Test fun theLastThirtyDaysEndToday() {
        val status = List(60) { if (it == 59) "done" else if (it == 58) "skipped" else "none" }
        val dots = recentDots(habit(status, List(60) { it == 58 }, "2026-08-28"), LocalDate.parse("2026-10-26"))
        assertEquals(30, dots.size)
        assertEquals(LocalDate.parse("2026-10-26"), dots.last().date)
        assertEquals("done", dots.last().status)
        assertEquals(DayDot(LocalDate.parse("2026-10-25"), "skipped", true), dots[28])
    }

    @Test fun anOlderServerStillShowsDoneDays() {
        val old = habit(emptyList()).copy(recentDays = listOf(0, 1), recentStatus = emptyList())
        val dots = recentDots(old, LocalDate.parse("2026-10-26"))
        assertEquals(listOf("none", "done"), dots.map { it.status })
        assertEquals(LocalDate.parse("2026-10-26"), dots.last().date)
    }

    @Test fun aHabitMovesWithinItsTab() {
        assertEquals(listOf("b", "a", "c"), movedIds(listOf("a", "b", "c"), "b", -1))
        assertEquals(listOf("a", "c", "b"), movedIds(listOf("a", "b", "c"), "b", 1))
        assertNull(movedIds(listOf("a", "b", "c"), "a", -1))
        assertNull(movedIds(listOf("a", "b", "c"), "c", 1))
    }

    @Test fun progressIsSaidForWeeksAndMonthsOnly() {
        val weekly = habit(emptyList()).copy(frequency = "weekly", target = 3, periodDone = 2)
        assertEquals("2 of 3 this week", periodProgress(weekly))
        assertNull(periodProgress(habit(emptyList())))
        assertEquals("daily", frequencyOf(habit(emptyList()).copy(frequency = "specific_days")))
    }
}
