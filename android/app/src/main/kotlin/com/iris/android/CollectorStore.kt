package com.iris.android

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.hardware.SensorEvent
import android.os.SystemClock
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import kotlin.math.abs
import org.json.JSONArray

/** Outgoing JSON, acknowledgement boundaries and health record keys commit atomically. */
internal class CollectorStore private constructor(ctx: Context) :
    SQLiteOpenHelper(ctx, "iris_collector.db", null, 1) {
    companion object {
        @Volatile private var instance: CollectorStore? = null
        fun get(ctx: Context): CollectorStore = instance ?: synchronized(this) {
            instance ?: CollectorStore(ctx.applicationContext).also { instance = it }
        }
    }

    data class Location(val id: Long, val reading: SensorPayloadBuilder.LocationReading)
    data class Steps(val date: LocalDate, val count: Int)
    data class PixelSnapshot(val locations: List<Location>, val steps: List<Steps>)
    data class Outgoing(val seq: Long, val kind: String, val json: String)
    data class HealthChunk(val json: String, val keys: List<String>)
    sealed interface HealthAdvance {
        data class Token(val token: String, val permissions: String, val sessionStart: Long) : HealthAdvance
        data class Recovery(val through: Instant) : HealthAdvance
    }
    data class HealthRecovery(val cursor: Instant, val until: Instant, val token: String)
    data class QueueStatus(
        val waitingPayloads: Int, val storedLocations: Int,
        val rejectedPayloads: Int, val lastRejection: String?,
    )

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execSQL("CREATE TABLE locations (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, accuracy INTEGER NOT NULL)")
        db.execSQL("CREATE TABLE daily_steps (date TEXT PRIMARY KEY, count INTEGER NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0, eligible INTEGER NOT NULL)")
        db.execSQL("CREATE TABLE outbox (seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL CHECK(kind IN ('pixel','health')), json TEXT NOT NULL, usage_through_ms INTEGER, through_location INTEGER, steps_json TEXT NOT NULL DEFAULT '[]', health_final INTEGER NOT NULL DEFAULT 0, health_token TEXT, health_permissions TEXT, health_session_start INTEGER, health_recovery_through TEXT)")
        db.execSQL("CREATE INDEX outbox_kind_seq ON outbox(kind, seq)")
        db.execSQL("CREATE TABLE outbox_health_keys (seq INTEGER NOT NULL, record_key TEXT NOT NULL)")
        db.execSQL("CREATE INDEX outbox_health_keys_seq ON outbox_health_keys(seq)")
        db.execSQL("CREATE TABLE health_seen (record_key TEXT PRIMARY KEY, seen_at INTEGER NOT NULL) WITHOUT ROWID")
        db.execSQL("CREATE TABLE rejected (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, status INTEGER NOT NULL, detail TEXT NOT NULL, rejected_at INTEGER NOT NULL)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        error("Collector database version $oldVersion is not supported; uninstall and reinstall IRIS")
    }

    override fun onDowngrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        error("Collector database version $oldVersion is not supported; uninstall and reinstall IRIS")
    }

    @Synchronized
    fun addLocation(ts: Instant, lat: Double, lon: Double, accuracyMeters: Int) {
        writableDatabase.insertOrThrow("locations", null, ContentValues().apply {
            put("ts", ts.toString())
            put("lat", lat)
            put("lon", lon)
            put("accuracy", accuracyMeters)
        })
    }

    /** A restarted service must not count steps taken while it was stopped. */
    @Synchronized
    fun resetStepBaseline() {
        writableDatabase.delete("state", "key IN ('step_raw','step_elapsed','step_boot','step_date')", null)
    }

    /** Each step event belongs to the sensor's wall-clock day, not callback time. */
    @Synchronized
    fun addSteps(event: SensorEvent) {
        val raw = event.values[0].toInt()
        if (raw < 0) return
        val now = System.currentTimeMillis()
        val eventMs = now + (event.timestamp - SystemClock.elapsedRealtimeNanos()) / 1_000_000
        val date = Instant.ofEpochMilli(eventMs).atZone(ZoneId.systemDefault()).toLocalDate()
        val db = writableDatabase
        db.beginTransaction()
        try {
            val previousRaw = state(db, "step_raw")?.toIntOrNull()
            val previousElapsed = state(db, "step_elapsed")?.toLongOrNull()
            val previousDate = state(db, "step_date")
            val bootTime = now - SystemClock.elapsedRealtime()
            val previousBoot = state(db, "step_boot")?.toLongOrNull()
            val sameBoot = previousRaw != null && previousElapsed != null &&
                previousBoot != null && abs(bootTime - previousBoot) < 120_000 &&
                event.timestamp > previousElapsed && raw >= previousRaw
            val dayChanged = previousDate != date.toString()
            val increment = if (sameBoot && !dayChanged) raw - previousRaw!! else 0
            val prior = db.rawQuery(
                "SELECT count FROM daily_steps WHERE date = ?", arrayOf(date.toString())
            ).use { if (it.moveToFirst()) it.getInt(0) else null }
            val count = (prior ?: 0) + increment
            val eligible = count > 0
            if (prior == null) {
                db.execSQL("INSERT INTO daily_steps(date,count,eligible) VALUES(?,?,?)",
                    arrayOf(date.toString(), count, if (eligible) 1 else 0))
            } else {
                db.execSQL("UPDATE daily_steps SET count = ?, eligible = ? WHERE date = ?",
                    arrayOf(count, if (eligible) 1 else 0, date.toString()))
            }
            putState(db, "step_raw", raw.toString())
            putState(db, "step_elapsed", event.timestamp.toString())
            putState(db, "step_boot", bootTime.toString())
            putState(db, "step_date", date.toString())
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    @Synchronized
    fun usageCursor(defaultValue: Long): Long {
        val db = writableDatabase
        val cursor = state(db, "usage_cursor")?.toLongOrNull()
            ?: state(db, "usage_origin")?.toLongOrNull()
            ?: defaultValue.also { putState(db, "usage_origin", it.toString()) }
        return maxOf(cursor, defaultValue)
    }

    @Synchronized
    fun advanceUsageCursor(through: Long) {
        putState(writableDatabase, "usage_cursor", through.toString())
    }

    @Synchronized
    fun healthToken(permissions: String, sessionStart: Long): String? {
        val db = readableDatabase
        return if (state(db, "health_permissions") == permissions &&
            state(db, "health_session_start") == sessionStart.toString())
            state(db, "health_token") else null
    }

    /** A prior cursor may have been restricted to Fitbit; replacing its token needs a wider replay. */
    @Synchronized
    fun hasHealthHistory(sessionStart: Long): Boolean {
        val db = readableDatabase
        return (state(db, "health_session_start") == sessionStart.toString() &&
            state(db, "health_token") != null) ||
            (state(db, "health_recovery_session") == sessionStart.toString() &&
                state(db, "health_recovery_token") != null)
    }

    @Synchronized
    fun healthRecovery(permissions: String, sessionStart: Long): HealthRecovery? {
        val db = readableDatabase
        if (state(db, "health_recovery_permissions") != permissions ||
            state(db, "health_recovery_session") != sessionStart.toString()) return null
        val cursor = state(db, "health_recovery_cursor") ?: return null
        val until = state(db, "health_recovery_until") ?: return null
        val token = state(db, "health_recovery_token") ?: return null
        return HealthRecovery(Instant.parse(cursor), Instant.parse(until), token)
    }

    @Synchronized
    fun beginHealthRecovery(token: String, permissions: String, sessionStart: Long,
                            since: Instant, until: Instant): HealthRecovery {
        val db = writableDatabase
        db.beginTransaction()
        try {
            putState(db, "health_recovery_token", token)
            putState(db, "health_recovery_permissions", permissions)
            putState(db, "health_recovery_session", sessionStart.toString())
            putState(db, "health_recovery_cursor", since.toString())
            putState(db, "health_recovery_until", until.toString())
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        return HealthRecovery(since, until, token)
    }

    private fun advanceHealthRecovery(db: SQLiteDatabase, through: Instant) {
        val until = Instant.parse(requireNotNull(state(db, "health_recovery_until")))
        if (through < until) {
            putState(db, "health_recovery_cursor", through.toString())
            return
        }
        val token = requireNotNull(state(db, "health_recovery_token"))
        val permissions = requireNotNull(state(db, "health_recovery_permissions"))
        val sessionStart = requireNotNull(state(db, "health_recovery_session"))
        db.delete("state", "key IN ('health_recovery_token','health_recovery_permissions'," +
            "'health_recovery_session','health_recovery_cursor','health_recovery_until')", null)
        putState(db, "health_token", token)
        putState(db, "health_permissions", permissions)
        putState(db, "health_session_start", sessionStart)
    }

    @Synchronized
    fun seenHealthKeys(keys: List<String>): Set<String> {
        if (keys.isEmpty()) return emptySet()
        val seen = mutableSetOf<String>()
        for (part in keys.chunked(800)) {
            val placeholders = List(part.size) { "?" }.joinToString(",")
            readableDatabase.rawQuery(
                "SELECT record_key FROM health_seen WHERE record_key IN ($placeholders)",
                part.toTypedArray(),
            ).use { cursor -> while (cursor.moveToNext()) seen.add(cursor.getString(0)) }
        }
        return seen
    }

    @Synchronized
    fun applyHealthAdvance(advance: HealthAdvance) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            applyHealthAdvance(db, advance)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
    }

    private fun applyHealthAdvance(db: SQLiteDatabase, advance: HealthAdvance) {
        when (advance) {
            is HealthAdvance.Token -> {
                putState(db, "health_token", advance.token)
                putState(db, "health_permissions", advance.permissions)
                putState(db, "health_session_start", advance.sessionStart.toString())
            }
            is HealthAdvance.Recovery -> advanceHealthRecovery(db, advance.through)
        }
    }

    @Synchronized
    fun snapshotPixel(locationLimit: Int): PixelSnapshot {
        val locations = mutableListOf<Location>()
        readableDatabase.rawQuery(
            "SELECT id, ts, lat, lon, accuracy FROM locations ORDER BY id LIMIT ?",
            arrayOf(locationLimit.toString()),
        ).use { cursor ->
            while (cursor.moveToNext()) locations.add(Location(cursor.getLong(0),
                SensorPayloadBuilder.LocationReading(
                    Instant.parse(cursor.getString(1)), cursor.getDouble(2), cursor.getDouble(3),
                    cursor.getInt(4))))
        }
        val steps = mutableListOf<Steps>()
        readableDatabase.rawQuery(
            "SELECT date, count FROM daily_steps WHERE eligible=1 AND count>acknowledged ORDER BY date", null
        ).use { cursor ->
            while (cursor.moveToNext()) steps.add(Steps(LocalDate.parse(cursor.getString(0)), cursor.getInt(1)))
        }
        return PixelSnapshot(locations, steps)
    }

    @Synchronized
    fun nextOutgoing(kind: String): Outgoing? = readableDatabase.rawQuery(
        "SELECT seq, json FROM outbox WHERE kind = ? ORDER BY seq LIMIT 1", arrayOf(kind)
    ).use { if (it.moveToFirst()) Outgoing(it.getLong(0), kind, it.getString(1)) else null }

    @Synchronized
    fun enqueuePixel(json: String, snapshot: PixelSnapshot, usageThroughMs: Long) {
        val steps = JSONArray().apply {
            snapshot.steps.forEach { put(JSONArray().put(it.date.toString()).put(it.count)) }
        }
        writableDatabase.insertOrThrow("outbox", null, ContentValues().apply {
            put("kind", "pixel")
            put("json", json)
            put("usage_through_ms", usageThroughMs)
            put("through_location", snapshot.locations.lastOrNull()?.id)
            put("steps_json", steps.toString())
        })
    }

    /**
     * A one-time app-usage history payload. It carries no cursor, location or
     * steps, so acknowledging it moves nothing the live collector relies on;
     * the laptop counts time it already has only once.
     */
    @Synchronized
    fun enqueueHistory(json: String) {
        writableDatabase.insertOrThrow("outbox", null, ContentValues().apply {
            put("kind", "pixel")
            put("json", json)
            put("steps_json", "[]")
        })
    }

    @Synchronized
    fun enqueueHealth(chunks: List<HealthChunk>, advance: HealthAdvance) {
        require(chunks.isNotEmpty())
        val db = writableDatabase
        db.beginTransaction()
        try {
            for ((index, chunk) in chunks.withIndex()) {
                val isFinal = index == chunks.lastIndex
                val seq = db.insertOrThrow("outbox", null, ContentValues().apply {
                    put("kind", "health")
                    put("json", chunk.json)
                    put("health_final", if (isFinal) 1 else 0)
                    if (isFinal) when (advance) {
                        is HealthAdvance.Token -> {
                            put("health_token", advance.token)
                            put("health_permissions", advance.permissions)
                            put("health_session_start", advance.sessionStart)
                        }
                        is HealthAdvance.Recovery ->
                            put("health_recovery_through", advance.through.toString())
                    }
                })
                for (key in chunk.keys) db.insertOrThrow("outbox_health_keys", null,
                    ContentValues().apply { put("seq", seq); put("record_key", key) })
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
    }

    @Synchronized
    fun acknowledge(seq: Long) = finish(seq, null, null)

    @Synchronized
    fun quarantine(seq: Long, status: Int, detail: String) = finish(seq, status, detail)

    private fun finish(seq: Long, status: Int?, detail: String?) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.rawQuery(
                "SELECT kind, usage_through_ms, through_location, steps_json, health_final, " +
                    "health_token, health_permissions, health_session_start, health_recovery_through " +
                    "FROM outbox WHERE seq = ?", arrayOf(seq.toString()),
            ).use { row ->
                check(row.moveToFirst()) { "No outgoing payload $seq" }
                val kind = row.getString(0)
                if (kind == "pixel") {
                    if (!row.isNull(2)) db.delete("locations", "id <= ?", arrayOf(row.getLong(2).toString()))
                    val steps = JSONArray(row.getString(3))
                    for (i in 0 until steps.length()) {
                        val item = steps.getJSONArray(i)
                        db.execSQL("UPDATE daily_steps SET acknowledged = MAX(acknowledged, ?) WHERE date = ?",
                            arrayOf(item.getInt(1), item.getString(0)))
                    }
                    if (!row.isNull(1)) putState(db, "usage_cursor", row.getLong(1).toString())
                } else {
                    val now = System.currentTimeMillis()
                    db.execSQL("INSERT OR IGNORE INTO health_seen(record_key, seen_at) " +
                        "SELECT record_key, ? FROM outbox_health_keys WHERE seq = ?",
                        arrayOf(now, seq))
                    db.delete("outbox_health_keys", "seq = ?", arrayOf(seq.toString()))
                    if (row.getInt(4) == 1) {
                        val advance = if (!row.isNull(8)) {
                            HealthAdvance.Recovery(Instant.parse(row.getString(8)))
                        } else {
                            HealthAdvance.Token(row.getString(5), row.getString(6), row.getLong(7))
                        }
                        applyHealthAdvance(db, advance)
                        db.delete("health_seen", "seen_at < ?",
                            arrayOf((now - 31L * 24 * 60 * 60_000).toString()))
                    }
                }
                if (status != null) {
                    db.insertOrThrow("rejected", null, ContentValues().apply {
                        put("kind", kind)
                        put("status", status)
                        put("detail", requireNotNull(detail))
                        put("rejected_at", System.currentTimeMillis())
                    })
                    db.execSQL("DELETE FROM rejected WHERE id NOT IN " +
                        "(SELECT id FROM rejected ORDER BY id DESC LIMIT 50)")
                }
            }
            db.delete("outbox", "seq = ?", arrayOf(seq.toString()))
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
    }

    @Synchronized
    fun queueStatus(): QueueStatus {
        val db = readableDatabase
        fun count(table: String): Int = db.rawQuery("SELECT count(*) FROM $table", null)
            .use { it.moveToFirst(); it.getInt(0) }
        val last = db.rawQuery("SELECT status, detail FROM rejected ORDER BY id DESC LIMIT 1", null)
            .use { if (it.moveToFirst()) "HTTP ${it.getInt(0)}: ${it.getString(1)}" else null }
        return QueueStatus(count("outbox"), count("locations"), count("rejected"), last)
    }

    private fun state(db: SQLiteDatabase, key: String): String? = db.rawQuery(
        "SELECT value FROM state WHERE key = ?", arrayOf(key)
    ).use { if (it.moveToFirst()) it.getString(0) else null }

    private fun putState(db: SQLiteDatabase, key: String, value: String) {
        db.insertWithOnConflict("state", null, ContentValues().apply {
            put("key", key)
            put("value", value)
        }, SQLiteDatabase.CONFLICT_REPLACE)
    }
}
