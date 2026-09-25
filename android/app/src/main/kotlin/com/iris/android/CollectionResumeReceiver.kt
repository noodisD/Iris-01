package com.iris.android

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** A reboot or update never silently restarts location collection. */
internal class CollectionResumeReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action !in setOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED) ||
            !Settings.collectionRequested(ctx)) return
        Settings.setCollectionEnabled(ctx, false)
        SyncState.recordProblem(ctx, SyncState.Problem.COLLECTION,
            "Collection stopped when the phone restarted or IRIS was updated. Tap Start to resume.")
        CollectorNotifications.postResume(ctx, "IRIS collection stopped",
            "The phone restarted or IRIS was updated. Tap to resume.")
    }
}
