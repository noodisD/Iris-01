package com.iris.android

import android.app.Activity
import android.content.Context
import android.os.Bundle
import android.view.ViewGroup
import android.widget.TextView
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.changes.UpsertionChange
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.request.ChangesTokenRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import java.time.Duration
import java.time.Instant
import kotlin.reflect.KClass

/** Reads permitted Health Connect measurements regardless of the writing app. */
object HealthConnectReader {
    private const val PAGE_SIZE = 500
    sealed interface ChangeRead {
        data object Expired : ChangeRead
        data class Page(
            val rows: Map<String, List<Map<String, Any>>>,
            val nextToken: String,
            val hasMore: Boolean,
        ) : ChangeRead
    }

    val requiredPermissions: Set<String> = setOf(
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(SleepSessionRecord::class),
        HealthPermission.getReadPermission(OxygenSaturationRecord::class),
    )

    fun isAvailable(ctx: Context): Boolean =
        HealthConnectClient.getSdkStatus(ctx) == HealthConnectClient.SDK_AVAILABLE

    /** Request this set through PermissionController's activity-result contract, on the UI thread. */
    fun requestablePermissions(ctx: Context): Set<String> {
        if (!isAvailable(ctx)) return emptySet()
        val client = try {
            HealthConnectClient.getOrCreate(ctx)
        } catch (e: UnsupportedOperationException) {
            return emptySet()
        } catch (e: IllegalStateException) {
            return emptySet()
        }
        return if (client.features.getFeatureStatus(
                HealthConnectFeatures.FEATURE_READ_HEALTH_DATA_IN_BACKGROUND
            ) == HealthConnectFeatures.FEATURE_STATUS_AVAILABLE
        ) requiredPermissions + HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND
        else requiredPermissions
    }

    /** Replay a bounded window; a token created first catches writes made during this read. */
    suspend fun readSince(ctx: Context, since: Instant, until: Instant):
        Map<String, List<Map<String, Any>>> {
        val (client, granted) = clientAndPermissions(ctx)
            ?: error("Health Connect background access is unavailable")
        if (!since.isBefore(until)) return emptyTiers()
        val heartRate = mutableListOf<Map<String, Any>>()
        val sleep = mutableListOf<Map<String, Any>>()
        val spo2 = mutableListOf<Map<String, Any>>()
        // Overlapping interval records are returned; only samples/ends inside
        // the consented window are emitted, without querying before its start.
        val range = TimeRangeFilter.between(since, until)
        if (HealthPermission.getReadPermission(HeartRateRecord::class) in granted) {
            readPages(client, HeartRateRecord::class, range) { record ->
                append(record, since, until, heartRate, sleep, spo2)
            }
        }
        if (HealthPermission.getReadPermission(SleepSessionRecord::class) in granted) {
            readPages(client, SleepSessionRecord::class, range) { record ->
                append(record, since, until, heartRate, sleep, spo2)
            }
        }
        if (HealthPermission.getReadPermission(OxygenSaturationRecord::class) in granted) {
            readPages(client, OxygenSaturationRecord::class, range) { record ->
                append(record, since, until, heartRate, sleep, spo2)
            }
        }
        return mapOf("heart_rate" to heartRate, "sleep" to sleep, "spo2" to spo2)
    }

    /** Changes are ordered by insertion, not measurement time: delayed provider sync is retained. */
    suspend fun readChanges(ctx: Context, token: String, since: Instant): ChangeRead? {
        val (client, _) = clientAndPermissions(ctx) ?: return null
        val response = client.getChanges(token)
        if (response.changesTokenExpired) return ChangeRead.Expired
        val heartRate = mutableListOf<Map<String, Any>>()
        val sleep = mutableListOf<Map<String, Any>>()
        val spo2 = mutableListOf<Map<String, Any>>()
        for (change in response.changes) {
            if (change is UpsertionChange) {
                append(change.record, since, null, heartRate, sleep, spo2)
            }
        }
        return ChangeRead.Page(
            mapOf("heart_rate" to heartRate, "sleep" to sleep, "spo2" to spo2),
            response.nextChangesToken, response.hasMore,
        )
    }

    suspend fun newChangesToken(ctx: Context): String? {
        val (client, granted) = clientAndPermissions(ctx) ?: return null
        return client.getChangesToken(changesTokenRequest(granted))
    }

    /** An empty origin filter subscribes to records from every permitted Health Connect provider. */
    internal fun changesTokenRequest(granted: Set<String>): ChangesTokenRequest {
        val types = mutableSetOf<KClass<out Record>>()
        if (HealthPermission.getReadPermission(HeartRateRecord::class) in granted)
            types += HeartRateRecord::class
        if (HealthPermission.getReadPermission(SleepSessionRecord::class) in granted)
            types += SleepSessionRecord::class
        if (HealthPermission.getReadPermission(OxygenSaturationRecord::class) in granted)
            types += OxygenSaturationRecord::class
        return ChangesTokenRequest(recordTypes = types)
    }

    suspend fun grantedPermissions(ctx: Context): Set<String> {
        if (!isAvailable(ctx)) return emptySet()
        return HealthConnectClient.getOrCreate(ctx).permissionController.getGrantedPermissions()
    }

    private suspend fun clientAndPermissions(ctx: Context): Pair<HealthConnectClient, Set<String>>? {
        if (!isAvailable(ctx)) return null
        val client = try {
            HealthConnectClient.getOrCreate(ctx)
        } catch (e: UnsupportedOperationException) {
            return null
        } catch (e: IllegalStateException) {
            return null
        }
        val granted = client.permissionController.getGrantedPermissions()
        if (granted.none { it in requiredPermissions }) return null
        if (client.features.getFeatureStatus(
                HealthConnectFeatures.FEATURE_READ_HEALTH_DATA_IN_BACKGROUND
            ) == HealthConnectFeatures.FEATURE_STATUS_AVAILABLE &&
            HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND !in granted
        ) return null
        return client to granted
    }

    private fun emptyTiers(): Map<String, List<Map<String, Any>>> =
        mapOf("heart_rate" to emptyList(), "sleep" to emptyList(), "spo2" to emptyList())

    internal fun append(
        record: Record, since: Instant?, until: Instant?,
        heartRate: MutableList<Map<String, Any>>, sleep: MutableList<Map<String, Any>>,
        spo2: MutableList<Map<String, Any>>,
    ) {
        fun inWindow(ts: Instant) =
            (since == null || ts.isAfter(since)) && (until == null || !ts.isAfter(until))
        val originPackage = record.metadata.dataOrigin.packageName
        when (record) {
            is HeartRateRecord -> record.samples.forEachIndexed { index, sample ->
                if (inWindow(sample.time)) heartRate.add(mapOf(
                    "ts" to sample.time.toString(),
                    "bpm" to sample.beatsPerMinute,
                    "origin_package" to originPackage,
                    "record_key" to recordKey("heart_rate", record, index.toString()),
                ))
            }
            is SleepSessionRecord -> {
                if (!inWindow(record.endTime)) return
                val stageSummary = record.stages.groupBy { stageName(it.stage) }
                    .map { (name, stages) ->
                        val duration = stages.fold(Duration.ZERO) { sum, stage ->
                            sum.plus(Duration.between(stage.startTime, stage.endTime))
                        }
                        "$name:${minutes(duration)}"
                    }.joinToString(" ")
                val awake = record.stages.asSequence()
                    .filter { it.stage == SleepSessionRecord.STAGE_TYPE_AWAKE ||
                        it.stage == SleepSessionRecord.STAGE_TYPE_AWAKE_IN_BED ||
                        it.stage == SleepSessionRecord.STAGE_TYPE_OUT_OF_BED }
                    .fold(Duration.ZERO) { sum, stage ->
                        sum.plus(Duration.between(stage.startTime, stage.endTime))
                    }
                val fields = mutableMapOf<String, Any>(
                    "ts" to record.endTime.toString(),
                    "total_minutes" to minutes(Duration.between(record.startTime, record.endTime).minus(awake)),
                    "origin_package" to originPackage,
                    "record_key" to recordKey("sleep", record),
                )
                if (stageSummary.isNotEmpty()) fields["stage_summary"] = stageSummary
                sleep.add(fields)
            }
            is OxygenSaturationRecord -> {
                if (inWindow(record.time)) spo2.add(mapOf(
                    "ts" to record.time.toString(),
                    "percent" to record.percentage.value,
                    "origin_package" to originPackage,
                    "record_key" to recordKey("spo2", record),
                ))
            }
        }
    }

    private fun recordKey(tier: String, record: Record, sample: String = ""): String =
        "$tier:${record.metadata.id}:${record.metadata.lastModifiedTime}:$sample"

    private fun minutes(duration: Duration): Double = duration.toMillis() / 60_000.0

    private fun stageName(stage: Int): String = when (stage) {
        SleepSessionRecord.STAGE_TYPE_DEEP -> "deep"
        SleepSessionRecord.STAGE_TYPE_LIGHT -> "light"
        SleepSessionRecord.STAGE_TYPE_REM -> "rem"
        SleepSessionRecord.STAGE_TYPE_AWAKE -> "awake"
        SleepSessionRecord.STAGE_TYPE_AWAKE_IN_BED -> "awake_in_bed"
        SleepSessionRecord.STAGE_TYPE_OUT_OF_BED -> "out_of_bed"
        SleepSessionRecord.STAGE_TYPE_SLEEPING -> "sleeping"
        else -> "unknown"
    }

    private suspend fun <T : Record> readPages(
        client: HealthConnectClient,
        recordType: KClass<T>,
        range: TimeRangeFilter,
        consume: (T) -> Unit,
    ) {
        var token: String? = null
        do {
            val page = client.readRecords(ReadRecordsRequest(
                recordType = recordType,
                timeRangeFilter = range,
                pageSize = PAGE_SIZE,
                pageToken = token,
            ))
            page.records.forEach(consume)
            token = page.pageToken
        } while (token != null)
    }
}

/** Health Connect permission-screen privacy rationale on Android 13 and Android 14+. */
class HealthPermissionsRationaleActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Why IRIS requests health data"
        setContentView(TextView(this).apply {
            text = "If you grant access, IRIS reads the heart rate, sleep and blood oxygen " +
                "types you permit from every provider in Health Connect and sends the " +
                "readings to your paired IRIS laptop over certificate-pinned HTTPS. " +
                "They are staged for your review, not automatically made into evidence. " +
                "You can stop collection in IRIS or revoke access in Health Connect at any time."
            textSize = 18f
            val padding = (24 * resources.displayMetrics.density).toInt()
            setPadding(padding, padding, padding, padding)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        })
    }
}
