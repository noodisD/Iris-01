package com.iris.android.ui.habits

import com.iris.android.api.Habit
import java.time.LocalDate

/** How many recent days the phone shows: 60 do not fit a phone's width. */
const val PHONE_DAYS = 30

/** A recent day as the row shows it. */
data class DayDot(val date: LocalDate, val status: String, val noted: Boolean)

/**
 * The last [count] days of a habit, oldest first, from what the server sent.
 * Without per-day statuses (an older server) a day is done or not.
 */
fun recentDots(habit: Habit, today: LocalDate = LocalDate.now(), count: Int = PHONE_DAYS): List<DayDot> {
    val status = habit.recentStatus.ifEmpty { habit.recentDays.map { if (it != 0) "done" else "none" } }
    if (status.isEmpty()) return emptyList()
    val start = habit.recentStart?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
        ?: today.minusDays((status.size - 1).toLong())
    return status.indices.map { i ->
        DayDot(start.plusDays(i.toLong()), status[i], habit.recentNotes.getOrElse(i) { false })
    }.takeLast(count)
}

/** The habits of one tab with one moved [delta] places, as the ids to send. Null when it cannot move. */
fun movedIds(ids: List<String>, id: String, delta: Int): List<String>? {
    val from = ids.indexOf(id)
    val to = from + delta
    if (from < 0 || to !in ids.indices) return null
    return ids.toMutableList().apply { add(to, removeAt(from)) }
}

/** Which tab a habit belongs on. */
fun frequencyOf(habit: Habit): String = if (habit.frequency in listOf("weekly", "monthly")) habit.frequency else "daily"

/** "2 of 3 this week" for a weekly or monthly habit; null for a daily one. */
fun periodProgress(habit: Habit): String? = when (frequencyOf(habit)) {
    "weekly" -> "${habit.periodDone} of ${habit.target} this week"
    "monthly" -> "${habit.periodDone} of ${habit.target} this month"
    else -> null
}
