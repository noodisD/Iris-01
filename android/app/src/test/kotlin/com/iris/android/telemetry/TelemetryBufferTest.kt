package com.iris.android.telemetry

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TelemetryBufferTest {
    @Test fun dropsTheOldestAndRestoresToTheFront() {
        val buffer = TelemetryBuffer(2)
        buffer.addSpan(JSONObject().put("name", "a"))
        buffer.addSpan(JSONObject().put("name", "b"))
        buffer.addSpan(JSONObject().put("name", "c"))
        val (drained, _) = buffer.drain()
        assertEquals(listOf("b", "c"), drained.map { it.getString("name") })
        buffer.restore(listOf(JSONObject().put("name", "b")), emptyList())
        buffer.addSpan(JSONObject().put("name", "d"))
        val (again, logs) = buffer.drain()
        assertEquals(listOf("b", "d"), again.map { it.getString("name") })
        assertTrue(logs.isEmpty())
    }

    @Test fun payloadNamesThePhone() {
        val body = JSONObject(TelemetryBuffer.payload(
            listOf(JSONObject().put("name", "GET /api/health")),
            emptyList(),
            JSONObject().put("collector", JSONObject().put("waiting_payloads", 1)),
        ))
        assertEquals("android", body.getString("source"))
        assertEquals(1, body.getJSONArray("spans").length())
        assertEquals(1, body.getJSONObject("state").getJSONObject("collector").getInt("waiting_payloads"))
        assertEquals("GET /api/patterns/{id}", TelemetryBuffer.routeName("GET", "/api/patterns/abc123"))
    }
}
