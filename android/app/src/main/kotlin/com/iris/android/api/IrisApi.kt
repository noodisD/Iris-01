package com.iris.android.api

import android.net.Network
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.URI
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okio.BufferedSink
import okio.source
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

val json = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
    isLenient = true
}

data class UploadPart(
    val name: String,
    val filename: String?,
    val mimeType: String?,
    val value: String?,
    val source: (() -> InputStream)?,
    val length: Long,
)

class IrisApi(
    baseUrl: String,
    private val bearer: String,
    publicKeySha256: String,
    network: Network?,
) {
    private val root = baseUrl.trimEnd('/')
    private val http: OkHttpClient = PinnedHttp.client(publicKeySha256, network)

    init {
        require(URI(root).scheme == "https") { "IRIS requires HTTPS" }
        require(bearer.length >= 32) { "Pair this phone in IRIS before connecting" }
    }

    suspend fun <T> send(
        method: String,
        path: String,
        body: String?,
        decoder: DeserializationStrategy<T>,
    ): T = withContext(Dispatchers.IO) {
        val requestBody = body?.toRequestBody(JSON)
            ?: if (method == "POST" || method == "PUT" || method == "PATCH") "".toRequestBody(JSON) else null
        val request = request("$root/api$path")
            .method(method, requestBody).build()
        respond(request, decoder, null)
    }

    fun sse(path: String, body: String): Flow<JsonObject> = flow {
        val request = request("$root/api$path", "text/event-stream")
            .post(body.toRequestBody(JSON)).build()
        withResponse(request) { response ->
            if (!response.isSuccessful) {
                throw apiError(response.code, response.body?.string(), "IRIS could not be reached.", root)
            }
            val source = response.body?.source()
                ?: throw IrisApiException(response.code, "empty", "IRIS could not be reached.")
            val parser = SseParser()
            while (true) {
                val line = source.readUtf8Line() ?: break
                val block = parser.feed(line) ?: continue
                emit(json.parseToJsonElement(block) as JsonObject)
            }
        }
    }.flowOn(Dispatchers.IO)

    suspend fun <T> upload(
        path: String,
        parts: List<UploadPart>,
        decoder: DeserializationStrategy<T>,
        onProgress: (Float) -> Unit,
    ): T = withContext(Dispatchers.IO) {
        val multipart = MultipartBody.Builder().setType(MultipartBody.FORM)
        for (part in parts) {
            val fileSource = part.source
            if (fileSource != null) {
                val fileBody = object : RequestBody() {
                    override fun contentType() = part.mimeType?.toMediaTypeOrNull() ?: OCTET_STREAM
                    override fun contentLength() = part.length
                    override fun writeTo(sink: BufferedSink) {
                        fileSource().use { input -> input.source().use { sink.writeAll(it) } }
                    }
                }
                multipart.addFormDataPart(part.name, part.filename, fileBody)
            } else {
                multipart.addFormDataPart(part.name, part.value ?: "")
            }
        }
        val request = request("$root/api$path")
            .post(CountingRequestBody(multipart.build(), onProgress)).build()
        respond(request, decoder, "The upload could not reach IRIS.")
    }

    suspend fun download(serverPath: String, target: File): Unit = withContext(Dispatchers.IO) {
        require(serverPath.startsWith("/")) { "Expected a root-relative recording path" }
        val request = request("$root$serverPath").get().build()
        target.parentFile?.mkdirs()
        val temporary = File.createTempFile("iris-", ".download", target.parentFile)
        try {
            withResponse(request) { response ->
                if (!response.isSuccessful) {
                    throw apiError(response.code, response.body?.string(), response.message, root)
                }
                val source = response.body?.source()
                    ?: throw IrisApiException(response.code, "empty", "The recording could not be downloaded.")
                temporary.outputStream().use { output ->
                    val buffer = ByteArray(8192)
                    while (true) {
                        kotlinx.coroutines.currentCoroutineContext().ensureActive()
                        val count = source.read(buffer)
                        if (count == -1) break
                        output.write(buffer, 0, count)
                    }
                }
            }
            if (!temporary.renameTo(target)) throw IOException("Could not save the recording to ${target.path}")
        } catch (error: IOException) {
            throw transportError(error, root)
        } finally {
            temporary.delete()
        }
    }

    private fun request(url: String, accept: String = "application/json"): Request.Builder =
        Request.Builder().url(url)
            .header("Authorization", "Bearer $bearer")
            .header("Accept", accept)

    private suspend fun <T> respond(
        request: Request,
        decoder: DeserializationStrategy<T>,
        fallback: String?,
    ): T = withResponse(request) { response ->
        if (!response.isSuccessful) {
            throw apiError(response.code, response.body?.string(), fallback ?: response.message, root)
        }
        if (decoder.descriptor.serialName == "kotlin.Unit") {
            @Suppress("UNCHECKED_CAST")
            return@withResponse Unit as T
        }
        val body = response.body?.string().orEmpty()
        if (body.isEmpty()) throw SerializationException("IRIS returned an empty response (HTTP ${response.code}).")
        json.decodeFromString(decoder, body)
    }

    /** Cancels an in-flight call and any blocking stream read when the coroutine is cancelled. */
    private suspend fun <T> withResponse(request: Request, block: suspend (Response) -> T): T = coroutineScope {
        val call = http.newCall(request)
        val cancelOnExit = launch {
            try { awaitCancellation() } finally { call.cancel() }
        }
        try {
            try {
                awaitResponse(call).use { block(it) }
            } catch (error: IOException) {
                throw transportError(error, root)
            }
        } finally {
            cancelOnExit.cancel()
            call.cancel()
        }
    }

    private suspend fun awaitResponse(call: Call): Response = suspendCancellableCoroutine { continuation ->
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, error: IOException) {
                if (continuation.isActive) continuation.resumeWithException(transportError(error, root))
            }

            override fun onResponse(call: Call, response: Response) {
                if (continuation.isActive) continuation.resume(response) { response.close() }
                else response.close()
            }
        })
    }

    private companion object {
        val JSON = "application/json".toMediaType()
        val OCTET_STREAM = "application/octet-stream".toMediaType()
    }
}
