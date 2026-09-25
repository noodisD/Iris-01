package com.iris.android

import com.iris.android.api.PinnedHttp
import com.iris.android.api.describeRefusal
import com.iris.android.api.pinMismatchMessage
import android.net.Network
import java.io.IOException
import java.net.URI
import java.security.cert.CertificateException
import java.time.Instant
import java.util.concurrent.TimeUnit.SECONDS
import javax.net.ssl.SSLException
import javax.net.ssl.SSLPeerUnverifiedException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject

sealed interface IrisResponse {
    data object Accepted : IrisResponse
    data class Rejected(val code: Int, val detail: String) : IrisResponse
    data class Blocked(val reason: String) : IrisResponse
    data class Unreachable(val reason: String) : IrisResponse
}

fun IrisResponse.describe(): String = when (this) {
    IrisResponse.Accepted -> "Delivered"
    is IrisResponse.Rejected -> "IRIS refused this data (HTTP $code: $detail)"
    is IrisResponse.Blocked -> reason
    is IrisResponse.Unreachable -> "IRIS not reachable: $reason"
}

/** Sensor sync client, bound to the network that reaches IRIS and pinned to the server key. */
class IrisApiClient(
    baseUrl: String,
    private val bearer: String,
    publicKeySha256: String,
    network: Network?,
) {
    private val root = baseUrl.trimEnd('/')
    private val http = PinnedHttp.client(publicKeySha256, network).newBuilder()
        .callTimeout(60, SECONDS).build()

    init {
        require(URI(root).scheme == "https") { "Sensor sync requires HTTPS" }
        require(bearer.length >= 32) { "Pair this phone in IRIS before connecting" }
    }

    fun checkConnection(): IrisResponse = request(Request.Builder()
        .url("$root/api/mobile/status")
        .header("Authorization", "Bearer $bearer").get().build(), checkStatus = true)

    /** Retries send identical bytes; sentAt reports current clock offset separately from the body. */
    fun pushSensorBatch(json: String, sentAt: Instant): IrisResponse = request(Request.Builder()
        .url("$root/api/mobile/sensor/intake")
        .header("Authorization", "Bearer $bearer")
        .header("X-Iris-Sent-At", sentAt.toString())
        .post(json.toRequestBody(JSON)).build())

    private fun request(request: Request, checkStatus: Boolean = false): IrisResponse = try {
        http.newCall(request).execute().use { response -> classify(response, checkStatus) }
    } catch (error: IOException) {
        when {
            error is SSLPeerUnverifiedException ||
                (error is SSLException && generateSequence(error as Throwable?) { it.cause }
                    .any { it is CertificateException }) -> IrisResponse.Blocked(pinMismatchMessage(root))
            else -> IrisResponse.Unreachable(error.message ?: error.javaClass.simpleName)
        }
    }

    private fun classify(response: Response, checkStatus: Boolean): IrisResponse {
        val body = response.body?.string()
        val payload = runCatching { JSONObject(body ?: "") }.getOrNull()
        val detail = payload?.optString("detail")?.takeIf { it.isNotBlank() } ?: response.message
        val code = response.code
        if (code in 200..299) {
            return if (!checkStatus || payload?.optString("status") == "connected") IrisResponse.Accepted
            else IrisResponse.Blocked("Unexpected reply from $root; is this IRIS?")
        }
        describeRefusal(code, detail, root)?.let { return IrisResponse.Blocked(it) }
        return when {
            code == 408 || code == 429 || code in 500..599 ->
                IrisResponse.Unreachable("HTTP $code: $detail")
            else -> IrisResponse.Rejected(code, detail)
        }
    }

    companion object {
        private val JSON = "application/json".toMediaType()
    }
}
