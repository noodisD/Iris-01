package com.iris.android

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

internal object CollectorNotifications {
    private const val SENSOR_CHANNEL = "iris_sensors"
    private const val ALERT_CHANNEL = "iris_collection_alerts"
    private const val RESUME_ID = 2

    private fun channels(ctx: Context) {
        val manager = ctx.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(
            SENSOR_CHANNEL, "IRIS sensors", NotificationManager.IMPORTANCE_LOW))
        manager.createNotificationChannel(NotificationChannel(
            ALERT_CHANNEL, "IRIS collection alerts", NotificationManager.IMPORTANCE_DEFAULT))
    }

    private fun openApp(ctx: Context) = PendingIntent.getActivity(
        ctx, 0,
        Intent(ctx, MainActivity::class.java)
            .putExtra(MainActivity.EXTRA_DESTINATION, MainActivity.DESTINATION_COLLECTOR)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    fun ongoing(ctx: Context): Notification {
        channels(ctx)
        val stop = PendingIntent.getService(ctx, 1,
            Intent(ctx, SensorCollectorService::class.java).setAction(SensorCollectorService.ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(ctx, SENSOR_CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_iris)
            .setContentTitle("IRIS is collecting")
            .setContentText("Tap to see sync status")
            .setContentIntent(openApp(ctx))
            .addAction(0, "Stop", stop)
            .setOngoing(true)
            .build()
    }

    fun postResume(ctx: Context, title: String, text: String) {
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(
                ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        channels(ctx)
        ctx.getSystemService(NotificationManager::class.java).notify(RESUME_ID,
            NotificationCompat.Builder(ctx, ALERT_CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_iris)
                .setContentTitle(title)
                .setContentText(text)
                .setContentIntent(openApp(ctx))
                .setAutoCancel(true)
                .build())
    }

    fun cancelResume(ctx: Context) {
        ctx.getSystemService(NotificationManager::class.java).cancel(RESUME_ID)
    }
}
