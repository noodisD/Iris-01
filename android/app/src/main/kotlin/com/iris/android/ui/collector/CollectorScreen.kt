package com.iris.android.ui.collector

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorManager
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.provider.Settings as AndroidSettings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import androidx.health.connect.client.PermissionController
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.iris.android.AppUsageReader
import com.iris.android.CollectorNotifications
import com.iris.android.CollectorStore
import com.iris.android.HealthConnectReader
import com.iris.android.HomeNetwork
import com.iris.android.IrisApiClient
import com.iris.android.IrisResponse
import com.iris.android.SensorCollectorService
import com.iris.android.Settings
import com.iris.android.SyncState
import com.iris.android.api.IrisLink
import com.iris.android.describe
import com.iris.android.ui.components.IrisScaffold
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Opt-in live collector setup. Pairing itself is approved on the laptop. */
@Composable
fun CollectorScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    var permissionRefresh by remember { mutableIntStateOf(0) }
    val runtimePermissions = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { permissionRefresh++ }
    val healthPermissions = rememberLauncherForActivityResult(
        PermissionController.createRequestPermissionResultContract(),
    ) { permissionRefresh++ }

    var url by remember { mutableStateOf(Settings.laptopBaseUrl(context)) }
    var pin by remember { mutableStateOf(Settings.publicKeySha256(context)) }
    var token by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var testing by remember { mutableStateOf(false) }
    var collecting by remember { mutableStateOf(Settings.collectionEnabled(context)) }
    var syncStatus by remember { mutableStateOf(SyncState.read(context)) }
    var queueStatus by remember { mutableStateOf<CollectorStore.QueueStatus?>(null) }
    var manualDetails by remember { mutableStateOf(false) }
    var healthGranted by remember { mutableStateOf<Set<String>>(emptySet()) }
    var healthPermissionError by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    fun testConnection() {
        testing = true
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                val host = Settings.laptopHost(context)
                val network = HomeNetwork.find(context, host)
                when {
                    host == null -> "Scan the pairing QR from IRIS Settings first"
                    network == null -> HomeNetwork.unreachable(host)
                    else -> runCatching {
                        IrisApiClient(Settings.laptopBaseUrl(context),
                            Settings.bearer(context),
                            Settings.publicKeySha256(context), network)
                            .checkConnection()
                    }.fold(
                        { if (it == IrisResponse.Accepted) "Connected securely to IRIS" else it.describe() },
                        { it.message ?: "Connection failed" },
                    )
                }
            }
            message = result
            testing = false
        }
    }

    LaunchedEffect(Unit) {
        while (true) {
            delay(5_000)
            val status = withContext(Dispatchers.IO) {
                SyncState.read(context) to CollectorStore.get(context).queueStatus()
            }
            syncStatus = status.first
            queueStatus = status.second
            collecting = Settings.collectionEnabled(context)
            permissionRefresh++
        }
    }
    LaunchedEffect(permissionRefresh) {
        val result = withContext(Dispatchers.IO) {
            runCatching { HealthConnectReader.grantedPermissions(context) }
        }
        result.onSuccess {
            healthGranted = it
            healthPermissionError = ""
        }.onFailure {
            healthPermissionError = it.message ?: "Health Connect permission check failed"
        }
    }
    // Reading the refresh state makes permission changes visible after
    // returning from Android Settings as well as runtime prompts.
    val refresh = permissionRefresh
    val locationGranted = refresh.let {
        ActivityCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ActivityCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
    }
    val activityGranted = ActivityCompat.checkSelfPermission(
        context, Manifest.permission.ACTIVITY_RECOGNITION,
    ) == PackageManager.PERMISSION_GRANTED
    val usageGranted = AppUsageReader.hasPermission(context)
    val healthAvailable = HealthConnectReader.isAvailable(context)
    val healthRequested = if (healthAvailable)
        HealthConnectReader.requestablePermissions(context) else emptySet()
    val healthGrants = healthGranted.intersect(HealthConnectReader.requiredPermissions).size
    val backgroundHealthNeeded = healthRequested.any {
        it !in HealthConnectReader.requiredPermissions
    }
    val backgroundHealthAllowed = healthRequested
        .filterNot { it in HealthConnectReader.requiredPermissions }
        .all { it in healthGranted }
    val stepCounterAvailable = (context.getSystemService(Context.SENSOR_SERVICE) as SensorManager)
        .getDefaultSensor(Sensor.TYPE_STEP_COUNTER) != null

    IrisScaffold(title = "Phone collector", kicker = "sensors · this phone", onBack = onBack) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(padding).padding(horizontal = 20.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Connect IRIS", style = MaterialTheme.typography.headlineMedium)
            Text(
                "On your laptop, open IRIS → Settings → Android live sensors. " +
                    "Scan its pairing QR while both devices are on your home Wi-Fi or on Tailscale.",
            )
            if (Settings.hasBearer(context)) {
                Text("Paired with ${Settings.laptopBaseUrl(context)}")
            }
            Button(onClick = {
                val options = GmsBarcodeScannerOptions.Builder()
                    .setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
                GmsBarcodeScanning.getClient(context, options).startScan()
                    .addOnSuccessListener { barcode ->
                        scope.launch {
                            val result = withContext(Dispatchers.IO) {
                                runCatching {
                                    Settings.applyPairingCode(context,
                                        requireNotNull(barcode.rawValue))
                                }
                            }
                            result.fold({ pairing ->
                                url = pairing.url
                                pin = pairing.key
                                token = ""
                                message = if (pairing.token == null)
                                    "IRIS address updated to ${pairing.url}. Testing…"
                                else "Paired with IRIS at ${pairing.url}. Testing…"
                                testConnection()
                                scope.launch { IrisLink.refresh(context) }
                            }, { error -> message = error.message ?: "Could not save pairing QR" })
                        }
                    }
                    .addOnFailureListener { error ->
                        message = "Scanner unavailable: ${error.message}. Use Enter details manually."
                    }
            }) { Text("Scan pairing QR") }
            Button(enabled = !testing, onClick = { testConnection() }) {
                Text(if (testing) "Connecting…" else "Test connection")
            }
            TextButton(onClick = { manualDetails = !manualDetails }) {
                Text("Enter details manually")
            }
            if (manualDetails) {
                OutlinedTextField(value = url, onValueChange = { url = it },
                    label = { Text("Laptop HTTPS address") },
                    singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = pin, onValueChange = { pin = it },
                    label = { Text("Server key SHA-256") },
                    singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = token, onValueChange = { token = it },
                    label = { Text("Pairing token (leave empty to keep the current one)") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true, modifier = Modifier.fillMaxWidth())
                Button(onClick = {
                    try {
                        Settings.save(context, url, token.ifBlank { null }, pin)
                        token = ""
                        message = "Connection saved. Test it before starting collection."
                        scope.launch { IrisLink.refresh(context) }
                    } catch (error: Exception) {
                        message = error.message ?: "Could not save connection"
                    }
                }) { Text("Save connection") }
            }

            Text("Choose what this phone may collect", style = MaterialTheme.typography.titleMedium)
            Text("Location: ${if (locationGranted) "allowed" else "permission needed"}")
            if (!LocationManagerCompat.isLocationEnabled(
                    context.getSystemService(LocationManager::class.java))) {
                Text("Location is turned off on this phone")
            }
            val autoResume = refresh.let { com.iris.android.backgroundLocationGranted(context) }
            Text("Resume after a restart or update: ${if (autoResume) "automatic (location allowed all the time)" else "tap Start each time"}")
            if (locationGranted && !autoResume) {
                // Android shows this as a choice in Settings, never as a dialog:
                // the owner picks "Allow all the time" there.
                TextButton(onClick = {
                    runtimePermissions.launch(arrayOf(Manifest.permission.ACCESS_BACKGROUND_LOCATION))
                }) { Text("Allow location all the time") }
            }
            Text("Phone steps: ${if (!stepCounterAvailable) "no step counter on this phone" else if (activityGranted) "allowed" else "permission needed"}")
            Text("Step counts are increments observed while IRIS runs, not full-day totals.")
            Button(onClick = {
                val permissions = mutableListOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                    Manifest.permission.ACTIVITY_RECOGNITION,
                )
                if (Build.VERSION.SDK_INT >= 33) {
                    permissions += Manifest.permission.POST_NOTIFICATIONS
                }
                runtimePermissions.launch(permissions.toTypedArray())
            }) { Text("Grant phone permissions") }
            Text("App usage: ${if (usageGranted) "allowed" else "grant Usage access in Android Settings"}")
            if (usageGranted && SensorCollectorService.running) {
                // Android keeps a detailed log for about ten days. Sending it
                // fills days when collection was off; time already delivered
                // is counted once on the laptop.
                TextButton(onClick = {
                    scope.launch {
                        message = try {
                            val sent = withContext(Dispatchers.IO) { com.iris.android.AppUsageHistory.send(context) }
                            if (sent == 0) "No app history found on this phone"
                            else "Sending $sent app-usage intervals from the last ${com.iris.android.AppUsageHistory.DAYS} days. Confirm them in IRIS Sensors."
                        } catch (error: Exception) {
                            error.message ?: "Could not read app history"
                        }
                    }
                }) { Text("Import app history (about ${com.iris.android.AppUsageHistory.DAYS} days)") }
            }
            TextButton(onClick = {
                context.startActivity(Intent(AndroidSettings.ACTION_USAGE_ACCESS_SETTINGS))
            }) { Text("Open Usage access") }
            if (!usageGranted) {
                Text("If the switch is greyed out (\"Restricted setting\"), open App info → ⋮ → Allow restricted settings.")
                TextButton(onClick = {
                    context.startActivity(Intent(AndroidSettings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.fromParts("package", context.packageName, null)))
                }) { Text("Open App info") }
            }
            Text(
                "Health Connect heart rate, sleep and oxygen saturation: " +
                    if (!healthAvailable) "Health Connect unavailable"
                    else "$healthGrants of 3 permitted in Health Connect",
            )
            if (healthAvailable) {
                if (backgroundHealthNeeded) Text(
                    "Background Health Connect access: " +
                        if (backgroundHealthAllowed) "allowed" else "permission needed",
                )
                if (healthPermissionError.isNotBlank()) Text(healthPermissionError)
                Button(enabled = healthRequested.isNotEmpty(), onClick = {
                    healthPermissions.launch(healthRequested)
                }) { Text("Grant Health Connect access") }
            }
            Text(
                "Collection sends permitted measurements only to your laptop, over home Wi-Fi or Tailscale. " +
                    "IRIS stages them for review; they never become evidence automatically.",
            )
            Text(when {
                SensorCollectorService.running -> "Collecting"
                collecting -> "Enabled but not running — tap Start"
                else -> "Stopped"
            })
            if (!SensorCollectorService.running) {
                Button(onClick = {
                    when {
                        !locationGranted -> message = "Grant location permission before starting the foreground collector"
                        !activityGranted -> message = "Grant activity recognition for phone steps before starting"
                        !usageGranted -> message = "Grant Usage access in Android Settings before starting"
                        !stepCounterAvailable -> message = "This phone has no step counter"
                        !Settings.hasBearer(context) ->
                            message = "Scan the pairing QR before starting"
                        else -> try {
                            Settings.setCollectionEnabled(context, true)
                            CollectorNotifications.cancelResume(context)
                            ContextCompat.startForegroundService(context,
                                Intent(context, SensorCollectorService::class.java))
                            collecting = true
                            message = "Starting collection"
                        } catch (error: Exception) {
                            Settings.setCollectionEnabled(context, false)
                            message = error.message ?: "Could not start collection"
                        }
                    }
                }) { Text("Start live collection") }
            } else {
                Button(onClick = {
                    context.startService(Intent(context, SensorCollectorService::class.java)
                        .setAction(SensorCollectorService.ACTION_STOP))
                    collecting = false
                }) { Text("Stop collection") }
            }
            Button(enabled = SensorCollectorService.running, onClick = {
                context.startService(Intent(context, SensorCollectorService::class.java)
                    .setAction(SensorCollectorService.ACTION_SYNC))
            }) { Text("Sync now") }
            Text("Sync status", style = MaterialTheme.typography.titleMedium)
            val formatter = DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                .withZone(ZoneId.systemDefault())
            fun displayTime(at: Instant?): String = at?.let(formatter::format) ?: "not yet"
            Text("Pixel last sent: ${displayTime(syncStatus.lastSentPixel)}")
            Text("Health Connect last sent: ${displayTime(syncStatus.lastSentHealth)}")
            Text("Last attempt: ${displayTime(syncStatus.lastAttempt)}")
            syncStatus.problem?.let { problem ->
                val prefix = when (problem) {
                    SyncState.Problem.WAITING -> "Waiting:"
                    SyncState.Problem.UNREACHABLE -> "Not reachable:"
                    SyncState.Problem.BLOCKED -> "Action needed:"
                    SyncState.Problem.COLLECTION -> "Collector:"
                }
                Text("$prefix ${syncStatus.message.orEmpty()}")
            }
            if (syncStatus.unreachableStreak >= 3)
                Text("If IRIS's address changed, scan the address QR in IRIS Settings.")
            queueStatus?.let { queue ->
                Text("Waiting to send: ${queue.waitingPayloads} payloads · ${queue.storedLocations} location fixes stored")
                if (queue.rejectedPayloads > 0)
                    Text("${queue.rejectedPayloads} payloads were refused by IRIS (latest: ${queue.lastRejection})")
            }
            if (message.isNotBlank()) Text(message)
        }
    }
}
