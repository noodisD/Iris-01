package com.iris.android.ui.importing

import android.Manifest
import android.content.pm.PackageManager
import android.media.MediaRecorder
import android.os.Build
import android.os.SystemClock
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.iris.android.R
import com.iris.android.ui.components.RecordingPlayer
import com.iris.android.ui.components.RecordingSource
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import java.io.File
import java.time.Instant
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Retains recorder and clip references for unmount cleanup even during a pending save. */
private class VoiceSession {
    var recorder: MediaRecorder? = null
    var clip: File? = null
    var startedAt: Instant? = null
    var clockStart = 0L

    fun release(stop: Boolean) {
        recorder?.let {
            if (stop) runCatching { it.stop() }
            it.release()
        }
        recorder = null
    }

    fun discard() {
        release(stop = true)
        clip?.delete()
        clip = null
        startedAt = null
    }
}

@Composable
fun VoiceRecorder(disabled: Boolean, onSave: suspend (file: File, recordedAt: String) -> Unit) {
    val context = LocalContext.current
    val colors = LocalIrisColors.current
    val scope = rememberCoroutineScope()
    val session = remember { VoiceSession() }
    var phase by remember { mutableStateOf("idle") }
    var error by remember { mutableStateOf<String?>(null) }
    var seconds by remember { mutableIntStateOf(0) }
    var level by remember { mutableFloatStateOf(0f) }

    fun start() {
        error = null
        try {
            val now = Instant.now()
            val directory = File(context.cacheDir, "voice").apply { mkdirs() }
            val file = File(directory, "recording-${now.toString().take(19)}.m4a")
            @Suppress("DEPRECATION")
            val recorder = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(context) else MediaRecorder()
            try {
                recorder.setAudioSource(MediaRecorder.AudioSource.MIC)
                recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                recorder.setAudioSamplingRate(44_100)
                recorder.setAudioEncodingBitRate(128_000)
                recorder.setOutputFile(file.absolutePath)
                recorder.prepare()
                recorder.start()
            } catch (e: Exception) {
                recorder.release()
                file.delete()
                throw e
            }
            session.recorder = recorder
            session.clip = file
            session.startedAt = now
            session.clockStart = SystemClock.elapsedRealtime()
            seconds = 0
            level = 0f
            phase = "recording"
        } catch (e: Exception) {
            session.discard()
            phase = "idle"
            error = "The microphone could not be opened."
        }
    }

    val requestMic = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) start() else {
            phase = "idle"
            error = "IRIS needs permission to use your microphone. Allow it in Android Settings and try again."
        }
    }

    DisposableEffect(session) { onDispose { session.discard() } }
    LaunchedEffect(phase) {
        if (phase == "recording") while (true) {
            seconds = ((SystemClock.elapsedRealtime() - session.clockStart) / 1000).toInt()
            level = runCatching { (session.recorder?.maxAmplitude ?: 0) / 32767f }.getOrDefault(0f).coerceIn(0f, 1f)
            delay(100)
        }
    }
    val pulse by rememberInfiniteTransition(label = "recording indicator").animateFloat(
        initialValue = 0.5f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1600), RepeatMode.Reverse), label = "opacity",
    )

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (error != null) Text(error!!, color = colors.rose, fontSize = 11.5.sp)
        when (phase) {
            "idle" -> Button(onClick = {
                error = null
                phase = "requesting"
                if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
                    start()
                else requestMic.launch(Manifest.permission.RECORD_AUDIO)
            }, enabled = !disabled) {
                Icon(painterResource(R.drawable.ic_mic), contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Record an entry")
            }
            "requesting" -> Text("Waiting for the microphone…", color = colors.ink3, fontSize = 12.sp)
            "recording" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Spacer(Modifier.width(8.dp).height(8.dp).alpha(pulse).background(colors.rose, CircleShape))
                Text("%02d:%02d".format(seconds / 60, seconds % 60), style = IrisType.mono, color = colors.ink)
                LinearProgressIndicator(progress = { level }, modifier = Modifier.weight(1f).height(3.dp), color = colors.sage,
                    trackColor = colors.lineSoft)
                OutlinedButton(onClick = {
                    try {
                        session.release(stop = true)
                        phase = "review"
                    } catch (e: Exception) {
                        session.discard()
                        error = "The microphone could not be opened."
                        phase = "idle"
                    }
                }) {
                    Icon(painterResource(R.drawable.ic_stop_circle), contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Stop")
                }
            }
            "review", "saving" -> session.clip?.let { clip ->
                RecordingPlayer(RecordingSource.Local(clip))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Button(onClick = {
                        phase = "saving"
                        scope.launch {
                            try {
                                onSave(clip, requireNotNull(session.startedAt).toString())
                                session.discard()
                                phase = "idle"
                            } catch (e: Exception) {
                                error = e.message ?: "The recording could not be saved."
                                phase = "review"
                            }
                        }
                    }, enabled = phase != "saving") { Text(if (phase == "saving") "saving…" else "Save and transcribe") }
                    TextButton(onClick = { session.discard(); error = null; phase = "idle" }, enabled = phase != "saving") {
                        Text("discard", color = colors.ink4)
                    }
                }
            }
        }
    }
}
