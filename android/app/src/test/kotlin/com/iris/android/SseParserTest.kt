package com.iris.android

import com.iris.android.api.SseParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SseParserTest {
    @Test fun yieldsBlocksInOrderAndJoinsMultilineDataWithoutSeparator() {
        val parser = SseParser()
        assertNull(parser.feed("data:  {\"text\":\"first\"}  "))
        assertEquals("{\"text\":\"first\"}", parser.feed(""))
        assertNull(parser.feed("data: A "))
        assertNull(parser.feed("data: B "))
        assertEquals("AB", parser.feed(""))
    }

    @Test fun ignoresMetadataAndEmptyBlocks() {
        val parser = SseParser()
        assertNull(parser.feed("event: message"))
        assertNull(parser.feed(": comment"))
        assertNull(parser.feed(""))
        assertNull(parser.feed("data:  ok  "))
        assertEquals("ok", parser.feed(""))
    }
}
