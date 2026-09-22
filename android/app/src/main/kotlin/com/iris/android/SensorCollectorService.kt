package com.iris.android

import android.app.Service
import android.content.Intent
import android.os.IBinder

/**
 * Foreground sensor service. The full implementation lands with the
 * sensor-collection task; this stub exists so the manifest can declare
 * the service and the build target has a real class to compile.
 */
class SensorCollectorService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null
}
