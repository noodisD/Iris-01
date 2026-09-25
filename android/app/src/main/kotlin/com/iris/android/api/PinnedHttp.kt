package com.iris.android.api

import android.net.Network
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit.SECONDS
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager
import okhttp3.OkHttpClient

internal object PinnedHttp {
    fun client(publicKeySha256: String, network: Network?): OkHttpClient {
        val hex = publicKeySha256.trim().lowercase()
        require(hex.matches(Regex("[0-9a-f]{64}"))) { "Invalid IRIS server key SHA-256" }
        val expected = ByteArray(32) { i -> hex.substring(i * 2, i * 2 + 2).toInt(16).toByte() }
        val trust = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {
                throw CertificateException("IRIS does not accept client certificates")
            }
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                val leaf = chain.firstOrNull() ?: throw CertificateException("No IRIS certificate")
                leaf.checkValidity()
                val digest = MessageDigest.getInstance("SHA-256").digest(leaf.publicKey.encoded)
                if (!MessageDigest.isEqual(digest, expected)) {
                    throw CertificateException("IRIS server key does not match the paired key")
                }
            }
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        }
        val tls = SSLContext.getInstance("TLS")
        tls.init(null, arrayOf<TrustManager>(trust), SecureRandom())
        // OkHttp still checks the certificate's IP SAN via its default hostname verifier.
        val builder = OkHttpClient.Builder().sslSocketFactory(tls.socketFactory, trust)
            .connectTimeout(3, SECONDS).readTimeout(120, SECONDS)
        if (network != null) builder.socketFactory(network.socketFactory)
        return builder.build()
    }
}
