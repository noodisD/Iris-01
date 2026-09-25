package com.iris.android

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HomeNetworkTest {
    private fun ip(a: Int, b: Int, c: Int, d: Int) = byteArrayOf(
        a.toByte(), b.toByte(), c.toByte(), d.toByte())

    @Test fun matchesOnlyAddressesCoveredByWifiPrefix() {
        assertTrue(ipv4Covers(ip(192, 168, 1, 0), 24, ip(192, 168, 1, 30)))
        assertFalse(ipv4Covers(ip(192, 168, 1, 0), 24, ip(192, 168, 2, 30)))
        assertTrue(ipv4Covers(ip(192, 168, 1, 0), 0, ip(10, 22, 33, 44)))
        assertFalse(ipv4Covers(ip(192, 168, 1, 30), 32, ip(192, 168, 1, 31)))
    }
}
