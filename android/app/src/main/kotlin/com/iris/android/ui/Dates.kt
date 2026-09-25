package com.iris.android.ui

import android.text.format.DateFormat
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException
import java.util.Locale

const val DAY_WITH_WEEKDAY = "EEEMMMdyyyy"
const val DAY_LONG = "MMMMdyyyy"

private val calendarDay = Regex("\\d{4}-\\d{2}-\\d{2}")

/** A calendar date is never shifted through UTC; only timestamps are converted to the reader's zone. */
internal fun eventDay(value: String, zone: ZoneId): LocalDate? {
    return try {
        if (calendarDay.matches(value)) LocalDate.parse(value)
        else {
            val instant = try {
                OffsetDateTime.parse(value).toInstant()
            } catch (_: DateTimeParseException) {
                Instant.parse(value)
            }
            instant.atZone(zone).toLocalDate()
        }
    } catch (_: DateTimeParseException) {
        null
    }
}

fun formatEventDate(value: String?, skeleton: String = DAY_WITH_WEEKDAY): String {
    if (value.isNullOrBlank()) return ""
    val day = eventDay(value, ZoneId.systemDefault()) ?: return value
    val pattern = DateFormat.getBestDateTimePattern(Locale.getDefault(), skeleton)
    return day.format(DateTimeFormatter.ofPattern(pattern, Locale.getDefault()))
}
