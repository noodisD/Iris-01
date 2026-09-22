package com.iris.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * Foreground sensor service: collects location, app usage, and steps,
 * buffers them, and on a 6-hour cadence (driven by WorkManager) pushes
 * a JSON payload through IrisApiClient to /api/mobile/sensor/intake.
 *
 * The JSON shape is produced by SensorPayloadBuilder (JVM-testable).
 * This class only does Android-side work: holding the foreground
 * notification, listening to sensors, and triggering the push.
 *
 * Permissions required (declared in AndroidManifest.xml):
 *   ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION
 *   ACTIVITY_RECOGNITION
 *   PACKAGE_USAGE_STATS (granted via Settings, not a runtime prompt)
 *   FOREGROUND_SERVICE, FOREGROUND_SERVICE_LOCATION, POST_NOTIFICATIONS
 */
class SensorCollectorService : Service(), SensorEventListener {

    private lateinit var api: IrisApiClient
    private lateinit var fused: FusedLocationProviderClient
    private val locationBuffer = mutableListOf<SensorPayloadBuilder.LocationReading>()
    private var lastStepCount: Int = 0
    private var stepBaseline: Int = -1

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val baseUrl = Settings.laptopBaseUrl(applicationContext)
        val bearer = Settings.bearer(applicationContext)
        api = IrisApiClient(baseUrl = baseUrl, bearer = bearer)
        fused = LocationServices.getFusedLocationProviderClient(this)
        startForeground(NOTIFICATION_ID, buildNotification())
        requestLocationUpdates()
        registerStepCounter()
    }

    override fun onDestroy() { super.onDestroy() }

    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type == Sensor.TYPE_STEP_COUNTER) {
            val raw = event.values[0].toInt()
            if (stepBaseline < 0) {
                stepBaseline = raw
            }
            lastStepCount = raw - stepBaseline
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun requestLocationUpdates() {
        val req = LocationRequest.Builder(
            Priority.PRIORITY_BALANCED_POWER_ACCURACY, 60_000L).build()
        try {
            fused.requestLocationUpdates(req, object : LocationCallback() {
                override fun onLocationResult(result: LocationResult) {
                    for (loc in result.locations) {
                        locationBuffer.add(
                            SensorPayloadBuilder.LocationReading(
                                ts = Instant.ofEpochMilli(loc.time),
                                lat = loc.latitude,
                                lon = loc.longitude,
                                accuracyMeters = loc.accuracy.toInt(),
                            ))
                    }
                }
            }, mainLooper)
        } catch (e: SecurityException) {
            // The owner hasn't granted location permission. The service
            // runs anyway — the next push will just have empty tiers.
        }
    }

    private fun registerStepCounter() {
        val sensorManager = getSystemService(SENSOR_SERVICE) as
                android.hardware.SensorManager
        val counter = sensorManager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER)
        sensorManager.registerListener(
            this, counter,
            android.hardware.SensorManager.SENSOR_DELAY_NORMAL)
    }

    /**
     * Build the current payload and push it to IRIS. Called by
     * WorkManager on a 6-hour cadence (or on charging, in a future
     * iteration). The buffer is cleared after a successful push;
     * a failed push keeps the readings for the next attempt.
     */
    fun pushBatch() {
        val today = LocalDate.now(ZoneId.systemDefault())
        val payload = SensorPayloadBuilder().build(
            location = locationBuffer.toList(),
            appUsage = emptyList(),  // populated by a follow-up
            steps = if (lastStepCount > 0) listOf(
                SensorPayloadBuilder.StepsReading(today, lastStepCount)
            ) else emptyList(),
        )
        try {
            api.pushSensorBatch(payload)
            locationBuffer.clear()
        } catch (e: Exception) {
            // WorkManager will retry. Don't crash the service.
        }
    }

    private fun buildNotification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "IRIS sensors",
                                NotificationManager.IMPORTANCE_LOW))
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("IRIS is observing")
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val CHANNEL_ID = "iris_sensors"
        private const val NOTIFICATION_ID = 1
    }
}
