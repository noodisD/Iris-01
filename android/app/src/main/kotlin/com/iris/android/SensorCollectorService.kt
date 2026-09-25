package com.iris.android

import android.Manifest
import android.app.AlarmManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import androidx.core.content.ContextCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import java.time.Instant
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.atomic.AtomicBoolean

/** Opt-in collection; Wi-Fi sync has a wakeful idle-safe alarm and a single serial worker. */
class SensorCollectorService : Service(), SensorEventListener {
    private lateinit var store: CollectorStore
    private lateinit var sync: SensorSync
    private lateinit var fused: FusedLocationProviderClient
    private lateinit var sensorManager: SensorManager
    private lateinit var collectorThread: HandlerThread
    private lateinit var collectorHandler: Handler
    private lateinit var syncExecutor: ExecutorService
    private lateinit var statusExecutor: ExecutorService
    private lateinit var alarms: AlarmManager
    private lateinit var connectivity: ConnectivityManager
    private lateinit var power: PowerManager
    private val syncQueued = AtomicBoolean(false)
    @Volatile private var lastSyncStart = 0L
    @Volatile private var collecting = false
    private var locationCallback: LocationCallback? = null
    private var wifiCallback: ConnectivityManager.NetworkCallback? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        store = CollectorStore.get(this)
        sync = SensorSync(applicationContext, store)
        fused = LocationServices.getFusedLocationProviderClient(this)
        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        alarms = getSystemService(AlarmManager::class.java)
        connectivity = getSystemService(ConnectivityManager::class.java)
        power = getSystemService(PowerManager::class.java)
        collectorThread = HandlerThread("iris-sensor-events").apply { start() }
        collectorHandler = Handler(collectorThread.looper)
        syncExecutor = Executors.newSingleThreadExecutor { job -> Thread(job, "iris-sensor-sync") }
        statusExecutor = Executors.newSingleThreadExecutor { job -> Thread(job, "iris-sensor-status") }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            Settings.setCollectionEnabled(this, false)
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_SYNC) {
            if (collecting) requestSync(force = true) else stopSelf(startId)
            return if (collecting) START_STICKY else START_NOT_STICKY
        }
        if (!Settings.collectionEnabled(this)) {
            stopSelf(startId)
            return START_NOT_STICKY
        }
        if (collecting) return START_STICKY
        val missing = when {
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) !=
                PackageManager.PERMISSION_GRANTED &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) !=
                PackageManager.PERMISSION_GRANTED -> "Location permission is not granted"
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACTIVITY_RECOGNITION) !=
                PackageManager.PERMISSION_GRANTED -> "Activity recognition permission is not granted"
            !AppUsageReader.hasPermission(this) -> "Usage access is not granted"
            sensorManager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER) == null ->
                "This phone has no step counter"
            else -> null
        }
        if (missing != null) {
            Settings.setCollectionEnabled(this, false)
            fail(missing)
            stopSelf(startId)
            return START_NOT_STICKY
        }
        try {
            startForeground(NOTIFICATION_ID, CollectorNotifications.ongoing(this))
        } catch (error: Exception) {
            if (error !is SecurityException && error !is IllegalStateException) throw error
            Settings.setCollectionEnabled(this, false)
            fail("Android did not allow IRIS to keep collecting (${error.javaClass.simpleName}). Tap Start to resume.", error)
            if (intent == null) CollectorNotifications.postResume(this, "IRIS collection stopped",
                "Android stopped the collector. Tap to resume.")
            stopSelf(startId)
            return START_NOT_STICKY
        }
        try {
            store.resetStepBaseline()
        } catch (error: Exception) {
            fail("Could not initialize the step counter: ${error.message}", error)
            Settings.setCollectionEnabled(this, false)
            stopSelf(startId)
            return START_NOT_STICKY
        }
        collecting = true
        val counter = requireNotNull(sensorManager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER))
        if (!sensorManager.registerListener(this, counter, SensorManager.SENSOR_DELAY_NORMAL,
                collectorHandler)) {
            fail("Could not register the step counter")
            Settings.setCollectionEnabled(this, false)
            stopSelf(startId)
            return START_NOT_STICKY
        }
        requestLocationUpdates()
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { requestSync(force = false) }
        }
        wifiCallback = callback
        connectivity.registerNetworkCallback(NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build(), callback, collectorHandler)
        running = true
        CollectorNotifications.cancelResume(this)
        requestSync(force = true)
        return START_STICKY
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (!collecting || event.sensor.type != Sensor.TYPE_STEP_COUNTER) return
        try { store.addSteps(event) }
        catch (error: Exception) { fail("Could not persist steps: ${error.message}", error) }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    private fun requestLocationUpdates() {
        val request = LocationRequest.Builder(Priority.PRIORITY_BALANCED_POWER_ACCURACY, 60_000L)
            .setMinUpdateIntervalMillis(30_000L).build()
        val callback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                if (!collecting) return
                for (location in result.locations) {
                    try {
                        store.addLocation(Instant.ofEpochMilli(location.time), location.latitude,
                            location.longitude, location.accuracy.toInt())
                    } catch (error: Exception) {
                        fail("Could not persist location: ${error.message}", error)
                    }
                }
            }
        }
        locationCallback = callback
        try {
            fused.requestLocationUpdates(request, callback, collectorThread.looper)
                .addOnFailureListener { error ->
                    fail("Location updates unavailable: ${error.message}", error)
                    Settings.setCollectionEnabled(this@SensorCollectorService, false)
                    stopSelf()
                }
        } catch (error: SecurityException) {
            fail("Location permission was revoked: ${error.message}", error)
            Settings.setCollectionEnabled(this, false)
            stopSelf()
        }
    }

    private fun requestSync(force: Boolean) {
        if (!collecting) return
        if (!force && SystemClock.elapsedRealtime() - lastSyncStart < WIFI_SYNC_DEBOUNCE_MS) return
        if (!syncQueued.compareAndSet(false, true)) return
        try {
            syncExecutor.execute {
                syncQueued.set(false)
                runSync()
            }
        } catch (_: RejectedExecutionException) {
            syncQueued.set(false)
        }
    }

    private fun runSync() {
        val lock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "IRIS:sensor-sync")
        try {
            lock.acquire(3 * 60_000L)
            lastSyncStart = SystemClock.elapsedRealtime()
            val now = Instant.now()
            val host = Settings.laptopHost(this)
            val network = HomeNetwork.find(this, host)
            if (network == null) {
                if (collecting) SyncState.recordAttempt(this, now, false, false,
                    SyncState.Problem.WAITING,
                    "Waiting for the Wi-Fi network that reaches IRIS at $host")
            } else {
                val report = sync.run(network, Settings.collectionStartedAt(this)) { collecting }
                if (collecting) SyncState.recordAttempt(this, now, report.sentPixel,
                    report.sentHealth, report.problem, report.message)
            }
        } catch (error: Throwable) {
            Log.e(TAG, "Sensor sync failed", error)
            if (collecting) runCatching { SyncState.recordAttempt(this, Instant.now(), false, false,
                SyncState.Problem.UNREACHABLE, "Sync failed: ${error.javaClass.simpleName}") }
        } finally {
            if (lock.isHeld) lock.release()
            if (collecting) alarms.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP,
                SystemClock.elapsedRealtime() + SYNC_INTERVAL_MS, syncIntent())
        }
    }

    private fun syncIntent() = PendingIntent.getService(this, REQUEST_SYNC,
        Intent(this, SensorCollectorService::class.java).setAction(ACTION_SYNC),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    private fun fail(message: String, error: Throwable? = null) {
        if (error != null) Log.e(TAG, message, error) else Log.e(TAG, message)
        if (statusExecutor.isShutdown) return
        try {
            statusExecutor.execute {
                try {
                    SyncState.recordProblem(applicationContext, SyncState.Problem.COLLECTION, message)
                } catch (statusError: Exception) {
                    Log.e(TAG, "Could not persist collection problem", statusError)
                }
            }
        } catch (_: RejectedExecutionException) { /* Callback raced with onDestroy. */ }
    }

    override fun onDestroy() {
        collecting = false
        running = false
        alarms.cancel(syncIntent())
        wifiCallback?.let { runCatching { connectivity.unregisterNetworkCallback(it) } }
        locationCallback?.let { fused.removeLocationUpdates(it) }
        sensorManager.unregisterListener(this)
        collectorHandler.removeCallbacksAndMessages(null)
        collectorThread.quitSafely()
        syncExecutor.shutdown()
        statusExecutor.shutdown()
        super.onDestroy()
    }

    companion object {
        const val ACTION_SYNC = "com.iris.android.action.SYNC"
        const val ACTION_STOP = "com.iris.android.action.STOP"
        @Volatile var running = false
            private set
        private const val TAG = "IrisSensorCollector"
        private const val NOTIFICATION_ID = 1
        private const val SYNC_INTERVAL_MS = 15 * 60_000L
        private const val WIFI_SYNC_DEBOUNCE_MS = 60_000L
        private const val REQUEST_SYNC = 2
    }
}
