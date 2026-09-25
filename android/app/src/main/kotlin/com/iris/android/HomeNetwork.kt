package com.iris.android

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import java.net.Inet4Address

/** Bind mobile sync only to the Wi-Fi interface on the laptop's own subnet. */
internal object HomeNetwork {
    fun find(ctx: Context, host: String?): Network? {
        val target = host?.split('.')?.takeIf { it.size == 4 }?.map { it.toIntOrNull() }
            ?.takeIf { it.all { part -> part != null && part in 0..255 } }
            ?.map { requireNotNull(it).toByte() }?.toByteArray() ?: return null
        val manager = ctx.getSystemService(ConnectivityManager::class.java)
        @Suppress("DEPRECATION")
        val networks = manager.allNetworks
        return networks.firstOrNull { network ->
            manager.getNetworkCapabilities(network)?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true &&
                manager.getLinkProperties(network)?.linkAddresses?.any { link ->
                    link.address is Inet4Address &&
                        ipv4Covers(link.address.address, link.prefixLength, target)
                } == true
        }
    }
}

internal fun ipv4Covers(prefixAddress: ByteArray, prefixLength: Int, target: ByteArray): Boolean {
    if (prefixAddress.size != 4 || target.size != 4 || prefixLength !in 0..32) return false
    fun number(bytes: ByteArray): Int = bytes.fold(0) { value, byte ->
        (value shl 8) or (byte.toInt() and 0xff)
    }
    val mask = if (prefixLength == 0) 0 else -1 shl (32 - prefixLength)
    return (number(prefixAddress) and mask) == (number(target) and mask)
}
