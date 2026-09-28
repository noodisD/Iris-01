package com.iris.android.telemetry

import android.content.Context
import android.os.Build
import com.iris.android.CollectorStore
import com.iris.android.Settings
import com.iris.android.SyncState
import java.io.PrintWriter
import java.io.StringWriter
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONObject

object Telemetry {
    val buffer = TelemetryBuffer()
    private val installed = AtomicBoolean(false)
    private const val PREFS = "iris_telemetry"

    fun install(ctx: Context) {
        if (!installed.compareAndSet(false, true)) return
        val app = ctx.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            val crash = JSONObject()
                .put("message", "${error.javaClass.simpleName}: ${error.message}")
                .put("exception", stack(error))
                .put("where", "uncaught")
            app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString("pending_crash", crash.toString()).commit()
            previous?.uncaughtException(thread, error)
        }
    }

    fun error(where: String, error: Throwable) {
        buffer.addLog(JSONObject()
            .put("at_ms", System.currentTimeMillis())
            .put("level", "ERROR")
            .put("message", "${error.javaClass.simpleName}: ${error.message}")
            .put("exception", stack(error))
            .put("trace_id", JSONObject.NULL)
            .put("span_id", JSONObject.NULL)
            .put("attributes", JSONObject().put("where", where)))
    }

    fun collectorState(ctx: Context): JSONObject {
        val queue = CollectorStore.get(ctx).queueStatus()
        val sync = SyncState.read(ctx)
        val info = ctx.packageManager.getPackageInfo(ctx.packageName, 0)
        return JSONObject()
            .put("collector", JSONObject()
                .put("waiting_payloads", queue.waitingPayloads)
                .put("stored_locations", queue.storedLocations)
                .put("rejected_payloads", queue.rejectedPayloads)
                .put("last_rejection", queue.lastRejection)
                .put("last_attempt", sync.lastAttempt?.toString())
                .put("last_sent_pixel", sync.lastSentPixel?.toString())
                .put("last_sent_health", sync.lastSentHealth?.toString())
                .put("problem", sync.problem?.name)
                .put("message", sync.message)
                .put("unreachable_streak", sync.unreachableStreak)
                .put("collection_enabled", Settings.collectionEnabled(ctx)))
            .put("app", JSONObject()
                .put("version_name", info.versionName)
                .put("version_code", info.longVersionCode)
                .put("sdk", Build.VERSION.SDK_INT)
                .put("model", Build.MODEL))
    }

    suspend fun flush(ctx: Context, send: suspend (String) -> Boolean) {
        val (spans, logs) = buffer.drain()
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val crash = prefs.getString("pending_crash", null)
        val sentLogs = logs.toMutableList()
        if (crash != null) {
            val parsed = JSONObject(crash)
            sentLogs.add(JSONObject()
                .put("at_ms", System.currentTimeMillis())
                .put("level", "ERROR")
                .put("message", parsed.optString("message"))
                .put("exception", parsed.optString("exception"))
                .put("attributes", JSONObject().put("where", parsed.optString("where"))))
        }
        if (spans.isEmpty() && sentLogs.isEmpty() && crash == null) {
            val stateOnly = TelemetryBuffer.payload(emptyList(), emptyList(), collectorState(ctx))
            if (!send(stateOnly)) return
            return
        }
        val body = TelemetryBuffer.payload(spans, sentLogs, collectorState(ctx))
        val ok = try { send(body) } catch (_: Exception) { false }
        if (!ok) buffer.restore(spans, logs)
        else if (crash != null) prefs.edit().remove("pending_crash").apply()
    }

    private fun stack(error: Throwable): String {
        val writer = StringWriter()
        error.printStackTrace(PrintWriter(writer))
        return writer.toString()
    }
}
