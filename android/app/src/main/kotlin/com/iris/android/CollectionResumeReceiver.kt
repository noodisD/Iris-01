package com.iris.android

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * After a restart or an update, collection resumes by itself only if the owner
 * allowed location "all the time"; Android forbids restarting location
 * collection from the background otherwise. Without it, or if Android refuses
 * anyway, collection stops and the owner is asked to tap to resume.
 */
internal class CollectionResumeReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action !in setOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED)) return
        when (resumeAction(Settings.collectionRequested(ctx), backgroundLocationGranted(ctx))) {
            ResumeAction.NOTHING -> return
            ResumeAction.RESUME -> {
                try {
                    Settings.setCollectionEnabled(ctx, true)
                    ContextCompat.startForegroundService(ctx, Intent(ctx, SensorCollectorService::class.java))
                    CollectorNotifications.cancelResume(ctx)
                    return
                } catch (error: Exception) {
                    // ForegroundServiceStartNotAllowedException or a SecurityException:
                    // fall through to asking, rather than failing silently.
                    Log.w("IRIS", "Collection could not resume by itself", error)
                }
            }
            ResumeAction.ASK -> Unit
        }
        Settings.setCollectionEnabled(ctx, false)
        SyncState.recordProblem(ctx, SyncState.Problem.COLLECTION,
            "Collection stopped when the phone restarted or IRIS was updated. Tap Start to resume.")
        CollectorNotifications.postResume(ctx, "IRIS collection stopped",
            "The phone restarted or IRIS was updated. Tap to resume.")
    }
}

internal enum class ResumeAction { NOTHING, RESUME, ASK }

/** What a restart or update does to collection: pure, so it can be tested. */
internal fun resumeAction(requested: Boolean, backgroundLocation: Boolean): ResumeAction = when {
    !requested -> ResumeAction.NOTHING
    backgroundLocation -> ResumeAction.RESUME
    else -> ResumeAction.ASK
}

internal fun backgroundLocationGranted(ctx: Context): Boolean =
    ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_BACKGROUND_LOCATION) ==
        PackageManager.PERMISSION_GRANTED
