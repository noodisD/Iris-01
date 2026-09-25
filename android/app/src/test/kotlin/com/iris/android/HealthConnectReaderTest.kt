package com.iris.android

import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.metadata.Metadata
import androidx.health.connect.client.units.percent
import java.time.Instant
import java.time.ZoneOffset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HealthConnectReaderTest {
    @Test fun changesTokenIncludesGrantedTypesWithoutRestrictingTheirProviders() {
        val permissions = HealthConnectReader.requiredPermissions
        val request = HealthConnectReader.changesTokenRequest(permissions)
        assertEquals(
            setOf(HeartRateRecord::class, SleepSessionRecord::class, OxygenSaturationRecord::class),
            request.recordTypes,
        )
        assertTrue(request.dataOriginFilters.isEmpty())

        val heartRateOnly = HealthConnectReader.changesTokenRequest(
            setOf(HealthPermission.getReadPermission(HeartRateRecord::class)))
        assertEquals(setOf(HeartRateRecord::class), heartRateOnly.recordTypes)
        assertTrue(heartRateOnly.dataOriginFilters.isEmpty())
    }

    @Test fun emitsRecordsOutsideFitbitWithTheirOriginWithinConsentedTime() {
        val since = Instant.parse("2026-01-01T12:00:00Z")
        val until = since.plusSeconds(900)
        val metadata = Metadata.manualEntryWithId("other-health-app")
        assertNotEquals("com.fitbit.FitbitMobile", metadata.dataOrigin.packageName)
        val heartRate = HeartRateRecord(
            startTime = since, startZoneOffset = ZoneOffset.UTC,
            endTime = since.plusSeconds(60), endZoneOffset = ZoneOffset.UTC,
            samples = listOf(HeartRateRecord.Sample(since.plusSeconds(30), 73)),
            metadata = metadata,
        )
        val sleep = SleepSessionRecord(
            startTime = since.minusSeconds(3600), startZoneOffset = ZoneOffset.UTC,
            endTime = since.plusSeconds(600), endZoneOffset = ZoneOffset.UTC,
            metadata = metadata,
        )
        val oxygen = OxygenSaturationRecord(
            time = since.plusSeconds(901), zoneOffset = ZoneOffset.UTC,
            percentage = 97.0.percent, metadata = metadata,
        )
        val heartRows = mutableListOf<Map<String, Any>>()
        val sleepRows = mutableListOf<Map<String, Any>>()
        val oxygenRows = mutableListOf<Map<String, Any>>()
        for (record in listOf(heartRate, sleep, oxygen)) {
            HealthConnectReader.append(record, since, until, heartRows, sleepRows, oxygenRows)
        }
        assertEquals(1, heartRows.size)
        assertEquals(73L, heartRows.single()["bpm"])
        assertEquals(metadata.dataOrigin.packageName, heartRows.single()["origin_package"])
        assertEquals(1, sleepRows.size)
        assertEquals(metadata.dataOrigin.packageName, sleepRows.single()["origin_package"])
        assertTrue(oxygenRows.isEmpty())
        HealthConnectReader.append(oxygen, since, until.plusSeconds(1), heartRows, sleepRows, oxygenRows)
        assertEquals(metadata.dataOrigin.packageName, oxygenRows.single()["origin_package"])
    }
}
