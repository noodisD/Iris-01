package com.iris.android

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import java.net.Inet4Address

/**
 * The network mobile sync is bound to. A laptop on the home network is reached
 * only over the Wi-Fi interface on its subnet. A laptop at its Tailscale address
 * (ADR-0022) is reached through the Tailscale VPN, over whatever carries it:
 * home Wi-Fi, another Wi-Fi, or mobile data.
 */
internal object HomeNetwork {
    fun find(ctx: Context, host: String?): Network? {
        val target = parseIpv4(host) ?: return null
        val manager = ctx.getSystemService(ConnectivityManager::class.java)
        @Suppress("DEPRECATION")
        val networks = manager.allNetworks
        val transport = if (isTailnet(target)) NetworkCapabilities.TRANSPORT_VPN
            else NetworkCapabilities.TRANSPORT_WIFI
        return networks.firstOrNull { network ->
            manager.getNetworkCapabilities(network)?.hasTransport(transport) == true &&
                manager.getLinkProperties(network)?.linkAddresses?.any { link ->
                    link.address is Inet4Address && if (isTailnet(target)) {
                        // Tailscale gives the phone a /32, so its own address
                        // being a tailnet address is what marks the right VPN.
                        isTailnet(link.address.address)
                    } else {
                        ipv4Covers(link.address.address, link.prefixLength, target)
                    }
                } == true
        }
    }

    fun isTailnet(host: String?): Boolean = parseIpv4(host)?.let(::isTailnet) == true

    /** The networks whose coming and going can change whether IRIS is reachable. */
    fun request(): NetworkRequest = NetworkRequest.Builder()
        .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
        .addTransportType(NetworkCapabilities.TRANSPORT_VPN)
        .removeCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)
        .build()

    /** Why there is no network to sync over, in the owner's terms. */
    fun unreachable(host: String?): String = if (isTailnet(host))
        "Can't reach IRIS at $host. Is Tailscale on and the laptop awake?"
    else "This phone is not on a Wi-Fi network that reaches IRIS at $host"
}

internal fun parseIpv4(host: String?): ByteArray? =
    host?.split('.')?.takeIf { it.size == 4 }?.map { it.toIntOrNull() }
        ?.takeIf { it.all { part -> part != null && part in 0..255 } }
        ?.map { requireNotNull(it).toByte() }?.toByteArray()

/** 100.64.0.0/10, the shared address space Tailscale assigns from. */
internal fun isTailnet(address: ByteArray): Boolean =
    ipv4Covers(byteArrayOf(100, 64, 0, 0), 10, address)

internal fun ipv4Covers(prefixAddress: ByteArray, prefixLength: Int, target: ByteArray): Boolean {
    if (prefixAddress.size != 4 || target.size != 4 || prefixLength !in 0..32) return false
    fun number(bytes: ByteArray): Int = bytes.fold(0) { value, byte ->
        (value shl 8) or (byte.toInt() and 0xff)
    }
    val mask = if (prefixLength == 0) 0 else -1 shl (32 - prefixLength)
    return (number(prefixAddress) and mask) == (number(target) and mask)
}
