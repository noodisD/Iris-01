package com.iris.android.telemetry

import java.io.IOException
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class TelemetryInterceptorTest {
    @Test fun recordsASuccessfulCallAndSkipsItsOwnPath() {
        val buffer = TelemetryBuffer()
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody("ok"))
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"accepted\":1}"))
        server.start()
        val client = OkHttpClient.Builder().addInterceptor(TelemetryInterceptor(buffer) { 1_000L }).build()
        client.newCall(okhttp3.Request.Builder().url(server.url("/api/patterns/abc123")).build()).execute().close()
        client.newCall(okhttp3.Request.Builder().url(server.url("/api/observatory/client-events")).build()).execute().close()
        val (spans, _) = buffer.drain()
        assertEquals(1, spans.size)
        assertEquals("GET /api/patterns/{id}", spans[0].getString("name"))
        assertEquals("ok", spans[0].getString("status"))
        val first = server.takeRequest()
        assertTrue(first.getHeader("traceparent")!!.matches(Regex("^00-[0-9a-f]{32}-[0-9a-f]{16}-01$")))
        assertEquals("android", first.getHeader("X-Iris-Client"))
        assertEquals(null, server.takeRequest().getHeader("traceparent"))
        server.shutdown()
    }

    @Test fun aConnectionFailureIsAnErrorSpanAndRethrows() {
        val buffer = TelemetryBuffer()
        val client = OkHttpClient.Builder().addInterceptor(TelemetryInterceptor(buffer)).build()
        assertThrows(IOException::class.java) {
            client.newCall(okhttp3.Request.Builder().url("http://127.0.0.1:1/api/health").build()).execute()
        }
        val (spans, _) = buffer.drain()
        assertEquals("error", spans.single().getString("status"))
    }
}
