package com.iris.android.telemetry

import java.security.SecureRandom
import org.json.JSONArray
import org.json.JSONObject

class TelemetryBuffer(private val capacity: Int = 500) {
    private val spans = ArrayDeque<JSONObject>()
    private val logs = ArrayDeque<JSONObject>()

    @Synchronized fun addSpan(span: JSONObject) { push(spans, span) }
    @Synchronized fun addLog(log: JSONObject) { push(logs, log) }
    @Synchronized fun isEmpty(): Boolean = spans.isEmpty() && logs.isEmpty()

    @Synchronized fun drain(): Pair<List<JSONObject>, List<JSONObject>> {
        val takenSpans = spans.toList()
        val takenLogs = logs.toList()
        spans.clear()
        logs.clear()
        return takenSpans to takenLogs
    }

    @Synchronized fun restore(spansBack: List<JSONObject>, logsBack: List<JSONObject>) {
        spansBack.asReversed().forEach { spans.addFirst(it) }
        logsBack.asReversed().forEach { logs.addFirst(it) }
        while (spans.size > capacity) spans.removeLast()
        while (logs.size > capacity) logs.removeLast()
    }

    private fun push(queue: ArrayDeque<JSONObject>, item: JSONObject) {
        if (queue.size >= capacity) queue.removeFirst()
        queue.addLast(item)
    }

    companion object {
        fun newTraceId(random: SecureRandom = SecureRandom()): String = hex(random, 16)
        fun newSpanId(random: SecureRandom = SecureRandom()): String = hex(random, 8)
        fun traceparent(traceId: String, spanId: String) = "00-$traceId-$spanId-01"

        fun routeName(method: String, path: String): String {
            val named = path.split("/").joinToString("/") { segment ->
                when {
                    segment.isEmpty() -> segment
                    segment.all { it.isDigit() } -> "{id}"
                    segment.any { it.isDigit() } && segment.length >= 6 -> "{id}"
                    else -> segment
                }
            }
            return "$method $named"
        }

        fun payload(spans: List<JSONObject>, logs: List<JSONObject>, state: JSONObject?): String {
            val body = JSONObject()
                .put("source", "android")
                .put("spans", JSONArray(spans))
                .put("logs", JSONArray(logs))
            if (state != null) body.put("state", state)
            return body.toString()
        }

        private fun hex(random: SecureRandom, bytes: Int): String {
            val buffer = ByteArray(bytes)
            random.nextBytes(buffer)
            return buffer.joinToString("") { "%02x".format(it) }
        }
    }
}
