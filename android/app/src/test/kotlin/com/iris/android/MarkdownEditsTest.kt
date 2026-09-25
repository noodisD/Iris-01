package com.iris.android

import com.iris.android.ui.journal.bold
import com.iris.android.ui.journal.bullet
import com.iris.android.ui.journal.heading
import com.iris.android.ui.journal.prefixLines
import com.iris.android.ui.journal.wrap
import org.junit.Assert.assertEquals
import org.junit.Test

class MarkdownEditsTest {
    @Test fun wrapPutsMarkersAroundASelection() {
        val edit = wrap("salt", 0, 4, "**")
        assertEquals("**salt**", edit.text)
        assertEquals(2, edit.start)
        assertEquals(6, edit.end)
    }

    @Test fun emptySelectionInsertsMarkersAndSitsBetweenThem() {
        val edit = bold("salt", 4, 4)
        assertEquals("salt****", edit.text)
        assertEquals(6, edit.start)
        assertEquals(6, edit.end)
    }

    @Test fun prefixLinesToggles() {
        val added = prefixLines("salt\npepper", 0, 11, "- ")
        assertEquals("- salt\n- pepper", added.text)
        val removed = bullet(added.text, 0, added.text.length)
        assertEquals("salt\npepper", removed.text)
    }

    @Test fun headingPrefixesTheSelectedLines() {
        assertEquals("## soup", heading("soup", 0, 4, 2).text)
    }
}
