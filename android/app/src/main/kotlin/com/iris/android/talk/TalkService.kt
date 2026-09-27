package com.iris.android.talk

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.iris.android.MainActivity
import com.iris.android.R
import com.iris.android.api.Conversation
import com.iris.android.api.json
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Keeps a spoken conversation going with the screen locked (ADR-0025): a
 * foreground service of type microphone, showing that IRIS is listening and
 * offering End. It holds TalkSession and stops when the conversation does.
 */
class TalkService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var watcher: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_END) {
            TalkSession.end(applicationContext)
            finish()
            return START_NOT_STICKY
        }
        val open = intent?.getStringExtra(EXTRA_CONVERSATION)
            ?.let { runCatching { json.decodeFromString(Conversation.serializer(), it) }.getOrNull() }
        if (open == null) { finish(); return START_NOT_STICKY }
        try {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } catch (error: Exception) {
            TalkSession.end(applicationContext,
                "Android did not let IRIS keep the microphone open (${error.javaClass.simpleName}). Open IRIS and start again.")
            finish()
            return START_NOT_STICKY
        }
        TalkSession.start(applicationContext, open)
        // The conversation can also end by itself: a microphone failure.
        watcher?.cancel()
        watcher = scope.launch {
            TalkSession.state.collect { state ->
                if (state.phase == TalkPhase.Error) {
                    TalkSession.end(applicationContext, state.error)
                    finish()
                }
            }
        }
        return START_NOT_STICKY
    }

    private fun finish() {
        watcher?.cancel()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        if (TalkSession.running) TalkSession.end(applicationContext)
        scope.cancel()
        super.onDestroy()
    }

    private fun notification(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "Talking with IRIS", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val end = PendingIntent.getService(this, 1,
            Intent(this, TalkService::class.java).setAction(ACTION_END), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_iris)
            .setContentTitle("Talking with IRIS")
            .setContentText("IRIS is listening. Only the words are kept.")
            .setContentIntent(open)
            .addAction(0, "End conversation", end)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .build()
    }

    companion object {
        private const val CHANNEL = "iris_talk"
        private const val NOTIFICATION_ID = 7
        private const val ACTION_END = "com.iris.android.talk.END"
        private const val EXTRA_CONVERSATION = "conversation"

        fun start(ctx: Context, conversation: Conversation) {
            ContextCompat.startForegroundService(ctx, Intent(ctx, TalkService::class.java)
                .putExtra(EXTRA_CONVERSATION, json.encodeToString(Conversation.serializer(), conversation)))
        }

        fun end(ctx: Context) {
            ctx.startService(Intent(ctx, TalkService::class.java).setAction(ACTION_END))
        }
    }
}
