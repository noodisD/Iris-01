package com.iris.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

class PairingCodeTest {
    private val url = "https://192.168.1.30:8765"
    private val key = "a".repeat(64)
    private val token = "b".repeat(64)

    @Test fun parsesFullPairingAndAddressCodes() {
        assertEquals(Settings.PairingCode(url, key, token),
            Settings.parsePairingCode("""{"iris":1,"url":"$url","key":"$key","token":"$token"}"""))
        assertNull(Settings.parsePairingCode("""{"iris":1,"url":"$url","key":"$key"}""").token)
    }

    @Test fun rejectsUnrelatedOrUnsupportedCodes() {
        assertThrows(IllegalArgumentException::class.java) {
            Settings.parsePairingCode("https://example.com")
        }
        assertThrows(IllegalArgumentException::class.java) {
            Settings.parsePairingCode("""{"iris":2,"url":"$url","key":"$key"}""")
        }
    }
}
