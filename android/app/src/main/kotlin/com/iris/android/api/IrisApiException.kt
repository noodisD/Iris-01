package com.iris.android.api

import java.io.IOException
import java.security.cert.CertificateException
import javax.net.ssl.SSLException
import javax.net.ssl.SSLPeerUnverifiedException
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

class IrisApiException(val status: Int, val code: String, override val message: String) : Exception(message)

internal fun apiError(status: Int, body: String?, fallback: String, root: String): IrisApiException {
    val payload = runCatching { json.parseToJsonElement(body ?: "") as? JsonObject }.getOrNull()
    val detailValue = payload?.get("detail")
    val detail = (detailValue as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    val firstMessage = ((detailValue as? JsonArray)?.firstOrNull() as? JsonObject)
        ?.get("msg")?.let { it as? JsonPrimitive }?.contentOrNull
    val message = (payload?.get("message") as? JsonPrimitive)?.contentOrNull
    val code = (payload?.get("code") as? JsonPrimitive)?.contentOrNull ?: "http_$status"
    return IrisApiException(status, code,
        describeRefusal(status, detail ?: fallback, root) ?: message ?: detail ?: firstMessage ?: fallback)
}

internal fun transportError(error: IOException, root: String): IrisApiException =
    if (error is SSLPeerUnverifiedException ||
        (error is SSLException && generateSequence(error as Throwable?) { it.cause }
            .any { it is CertificateException })) {
        IrisApiException(0, "pin", pinMismatchMessage(root))
    } else {
        IrisApiException(0, "unreachable", "IRIS not reachable: ${error.message ?: error.javaClass.simpleName}")
    }
