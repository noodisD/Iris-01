package com.iris.android

import android.content.Context
import android.net.Network
import java.time.Duration
import java.time.Instant
import java.time.temporal.ChronoUnit
import kotlinx.coroutines.runBlocking
import org.json.JSONObject

/** Drain durable payloads in source order; only acknowledgements advance local cursors. */
internal class SensorSync(private val ctx: Context, private val store: CollectorStore) {
    companion object {
        const val LOCATIONS_PER_PAYLOAD = 500
        const val HEALTH_READINGS_PER_PAYLOAD = 2_000
        const val USAGE_WINDOW_MS = 6L * 60 * 60_000
        val RECOVERY_WINDOW: Duration = Duration.ofHours(6)
        const val RECOVERY_WINDOWS_PER_BUILD = 20
        const val STEPS_PER_KIND = 16
    }

    data class Report(
        val sentPixel: Boolean, val sentHealth: Boolean,
        val problem: SyncState.Problem?, val message: String?,
    )

    fun run(network: Network, sessionStart: Long, keepGoing: () -> Boolean): Report {
        val api = try {
            IrisApiClient(Settings.laptopBaseUrl(ctx), Settings.bearer(ctx),
                Settings.publicKeySha256(ctx), network)
        } catch (error: IllegalArgumentException) {
            return Report(false, false, SyncState.Problem.BLOCKED,
                "Pair this phone with IRIS again: ${error.message}")
        } catch (error: IllegalStateException) {
            return Report(false, false, SyncState.Problem.BLOCKED,
                "Pair this phone with IRIS again: ${error.message}")
        }
        var sentPixel = false
        var sentHealth = false
        var problem: SyncState.Problem? = null
        var message: String? = null
        for (kind in listOf("pixel", "health")) {
            if (!keepGoing()) break
            if (kind == "health" && store.nextOutgoing("health") == null &&
                !HealthConnectReader.isAvailable(ctx)) continue
            for (step in 0 until STEPS_PER_KIND) {
                if (!keepGoing()) break
                var outgoing = store.nextOutgoing(kind)
                if (outgoing == null) {
                    val more = try {
                        if (kind == "pixel") buildPixel(sessionStart) else buildHealth(sessionStart)
                    } catch (error: Exception) {
                        problem = SyncState.Problem.COLLECTION
                        message = "${if (kind == "pixel") "Pixel" else "Health Connect"} read failed: " +
                            (error.message ?: error.javaClass.simpleName)
                        break
                    }
                    outgoing = store.nextOutgoing(kind)
                    if (outgoing == null) {
                        if (more) continue
                        break
                    }
                }
                if (!keepGoing()) break
                when (val response = api.pushSensorBatch(
                    outgoing.json, Instant.now().truncatedTo(ChronoUnit.SECONDS))) {
                    IrisResponse.Accepted -> {
                        store.acknowledge(outgoing.seq)
                        if (kind == "pixel") sentPixel = true else sentHealth = true
                    }
                    is IrisResponse.Rejected -> store.quarantine(
                        outgoing.seq, response.code, response.detail)
                    is IrisResponse.Blocked -> return Report(
                        sentPixel, sentHealth, SyncState.Problem.BLOCKED, response.reason)
                    is IrisResponse.Unreachable -> return Report(
                        sentPixel, sentHealth, SyncState.Problem.UNREACHABLE, response.reason)
                }
            }
        }
        return Report(sentPixel, sentHealth, problem, message)
    }

    private fun buildPixel(sessionStart: Long): Boolean {
        val now = System.currentTimeMillis()
        val cursor = minOf(store.usageCursor(sessionStart), now)
        val through = minOf(now, cursor + USAGE_WINDOW_MS)
        val usage = if (AppUsageReader.hasPermission(ctx) && through > cursor)
            AppUsageReader.read(ctx, cursor, through) else emptyList()
        val snapshot = store.snapshotPixel(LOCATIONS_PER_PAYLOAD)
        if (snapshot.locations.isEmpty() && snapshot.steps.isEmpty() && usage.isEmpty()) {
            if (through <= cursor) return false
            store.advanceUsageCursor(through)
            return through < now
        }
        val payload = SensorPayloadBuilder().build(
            exportedAt = Instant.ofEpochMilli(now),
            location = snapshot.locations.map { it.reading },
            appUsage = usage,
            steps = snapshot.steps.map {
                SensorPayloadBuilder.StepsReading(it.date, it.count, observed = true)
            },
        )
        store.enqueuePixel(JSONObject(payload).toString(), snapshot, through)
        return true
    }

    private fun buildHealth(sessionStart: Long): Boolean {
        val granted = runBlocking { HealthConnectReader.grantedPermissions(ctx) }
        val allowedTypes = granted.intersect(HealthConnectReader.requiredPermissions)
        if (allowedTypes.isEmpty()) return false
        // Versioning prevents a pre-upgrade Fitbit-only token or recovery from hiding other apps.
        val permissions = "all-providers-v1:" + allowedTypes.sorted().joinToString("|")
        val since = Instant.ofEpochMilli(sessionStart)
        var recovery = store.healthRecovery(permissions, sessionStart)
        if (recovery == null) {
            val token = store.healthToken(permissions, sessionStart)
            if (token != null) {
                when (val page = runBlocking { HealthConnectReader.readChanges(ctx, token, since) }) {
                    null -> return false
                    is HealthConnectReader.ChangeRead.Page -> return enqueueHealth(
                        page.rows, CollectorStore.HealthAdvance.Token(
                            page.nextToken, permissions, sessionStart)) || page.hasMore
                    HealthConnectReader.ChangeRead.Expired -> Unit
                }
            }
            // Create the unrestricted token first so delayed provider writes replay after recovery.
            val newToken = runBlocking { HealthConnectReader.newChangesToken(ctx) } ?: return false
            val until = Instant.now()
            // An old Fitbit-only cursor requires re-reading every still-readable day in this
            // consent session. Health Connect normally limits historical reads to 30 days.
            val lookback = if (token == null && !store.hasHealthHistory(sessionStart))
                Duration.ofDays(1) else Duration.ofDays(29)
            recovery = store.beginHealthRecovery(newToken, permissions, sessionStart,
                maxOf(since, until.minus(lookback)), until)
        }
        repeat(RECOVERY_WINDOWS_PER_BUILD) {
            val active = recovery ?: return true
            if (active.cursor >= active.until) {
                store.applyHealthAdvance(CollectorStore.HealthAdvance.Recovery(active.until))
                return true
            }
            val through = minOf(active.cursor.plus(RECOVERY_WINDOW), active.until)
            val rows = runBlocking { HealthConnectReader.readSince(ctx, active.cursor, through) }
            if (enqueueHealth(rows, CollectorStore.HealthAdvance.Recovery(through))) return true
            recovery = store.healthRecovery(permissions, sessionStart)
            if (recovery == null) return true
        }
        return true
    }

    private fun enqueueHealth(rows: Map<String, List<Map<String, Any>>>,
                              advance: CollectorStore.HealthAdvance): Boolean {
        val keys = SensorPayloadBuilder.TIER_ORDER.flatMap { tier ->
            rows[tier].orEmpty().map { it["record_key"] as String }
        }
        val seen = store.seenHealthKeys(keys)
        val fresh = SensorPayloadBuilder.TIER_ORDER.associateWith { tier ->
            rows[tier].orEmpty().filter { it["record_key"] !in seen }
        }
        if (fresh.values.all { it.isEmpty() }) {
            store.applyHealthAdvance(advance)
            return false
        }
        val chunks = SensorPayloadBuilder.chunkTiers(fresh, HEALTH_READINGS_PER_PAYLOAD)
            .map { tiers ->
                CollectorStore.HealthChunk(
                    JSONObject(SensorPayloadBuilder.health(Instant.now(), tiers)).toString(),
                    SensorPayloadBuilder.TIER_ORDER.flatMap { tier ->
                        tiers.getValue(tier).map { it["record_key"] as String }
                    },
                )
            }
        store.enqueueHealth(chunks, advance)
        return true
    }
}
