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

    @Test fun recognisesOnlyTheTailscaleRange() {
        assertTrue(isTailnet(ip(100, 64, 0, 1)))
        assertTrue(isTailnet(ip(100, 109, 145, 71)))
        assertTrue(isTailnet(ip(100, 127, 255, 255)))
        assertFalse(isTailnet(ip(100, 63, 255, 255)))
        assertFalse(isTailnet(ip(100, 128, 0, 1)))
        assertFalse(isTailnet(ip(192, 168, 1, 30)))
    }

    @Test fun readsHostsAsTailnetOnlyWhenTheyAreAddresses() {
        assertTrue(HomeNetwork.isTailnet("100.109.145.71"))
        assertFalse(HomeNetwork.isTailnet("192.168.1.30"))
        assertFalse(HomeNetwork.isTailnet("100.109.145"))
        assertFalse(HomeNetwork.isTailnet("100.300.1.1"))
        assertFalse(HomeNetwork.isTailnet(null))
    }

    @Test fun explainsAnUnreachableLaptopByHowItIsReached() {
        assertTrue(HomeNetwork.unreachable("100.109.145.71").contains("Tailscale"))
        assertTrue(HomeNetwork.unreachable("192.168.1.30").contains("Wi-Fi"))
    }
}
