package com.iris.android

import com.iris.android.ui.eventDay
import java.time.LocalDate
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class EventDayTest {
    @Test fun calendarDateNeverShiftsWithTimezone() {
        val day = LocalDate.of(2026, 5, 10)
        assertEquals(day, eventDay("2026-05-10", ZoneId.of("America/Los_Angeles")))
        assertEquals(day, eventDay("2026-05-10", ZoneId.of("Pacific/Auckland")))
    }

    @Test fun timestampIsConvertedIntoLocalDay() {
        assertEquals(LocalDate.of(2026, 5, 9), eventDay("2026-05-10T05:00:00Z", ZoneId.of("America/Los_Angeles")))
        assertNull(eventDay("not a date", ZoneId.of("Pacific/Auckland")))
    }
}
