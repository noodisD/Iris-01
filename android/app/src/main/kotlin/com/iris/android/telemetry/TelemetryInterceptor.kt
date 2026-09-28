package com.iris.android.telemetry

import java.io.IOException
import okhttp3.Interceptor
import okhttp3.Response
import org.json.JSONObject

class TelemetryInterceptor(
    private val buffer: TelemetryBuffer,
    private val clock: () -> Long = System::currentTimeMillis,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        if (request.url.encodedPath == "/api/observatory/client-events") return chain.proceed(request)
        val traceId = TelemetryBuffer.newTraceId()
        val spanId = TelemetryBuffer.newSpanId()
        val started = clock()
        val traced = request.newBuilder()
            .header("traceparent", TelemetryBuffer.traceparent(traceId, spanId))
            .header("X-Iris-Client", "android")
            .build()
        return try {
            val response = chain.proceed(traced)
            record(traceId, spanId, traced.method, traced.url.encodedPath, started, clock() - started,
                if (response.code >= 500) "error" else "ok",
                if (response.code >= 500) "HTTP ${response.code}" else null,
                response.code, response.header("content-type")?.startsWith("text/event-stream") == true)
            response
        } catch (error: IOException) {
            record(traceId, spanId, traced.method, traced.url.encodedPath, started, clock() - started,
                "error", "${error.javaClass.simpleName}: ${error.message}", 0, false)
            throw error
        }
    }

    private fun record(
        traceId: String, spanId: String, method: String, path: String, started: Long, duration: Long,
        status: String, message: String?, code: Int, streaming: Boolean,
    ) {
        buffer.addSpan(JSONObject()
            .put("trace_id", traceId)
            .put("span_id", spanId)
            .put("parent_span_id", JSONObject.NULL)
            .put("name", TelemetryBuffer.routeName(method, path))
            .put("started_at_ms", started)
            .put("duration_ms", duration)
            .put("status", status)
            .put("status_message", message ?: JSONObject.NULL)
            .put("attributes", JSONObject()
                .put("http.response.status_code", code)
                .put("url.path", path)
                .put("iris.client.streaming", streaming)))
    }
}
