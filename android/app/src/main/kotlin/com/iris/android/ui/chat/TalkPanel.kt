package com.iris.android.ui.chat

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.iris.android.api.IrisLink
import com.iris.android.talk.TalkPhase
import com.iris.android.talk.TalkSession
import com.iris.android.ui.components.IrisOrb
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.serialization.Serializable

@Serializable
private data class VoiceEstimate(val model: String, val perTurn: String)

private fun says(phase: TalkPhase) = when (phase) {
    TalkPhase.Off -> ""
    TalkPhase.Starting -> "Getting the microphone ready"
    TalkPhase.Listening, TalkPhase.Hearing -> "Listening"
    TalkPhase.Thinking -> "Thinking"
    TalkPhase.Speaking -> "IRIS is speaking"
    TalkPhase.Paused -> "Paused"
    TalkPhase.Error -> "Talking stopped"
}

/**
 * Before anything is sent: what talking sends where, and what a turn costs
 * (ADR-0025). The microphone is asked for only on Start talking.
 */
@Composable
fun TalkIntro(onStart: () -> Unit, onCancel: () -> Unit) {
    val context = LocalContext.current
    var cost by remember { mutableStateOf("Working out the cost…") }
    LaunchedEffect(Unit) {
        cost = try {
            val e = IrisLink.api().send("GET", "/voice/estimate", null, VoiceEstimate.serializer())
            "${e.perTurn}, on ${e.model}."
        } catch (e: Exception) { com.iris.android.telemetry.Telemetry.error("TalkPanel.cost", e); "The cost could not be worked out." }
    }
    val permissions = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        if (granted[Manifest.permission.RECORD_AUDIO] == true) onStart() else onCancel()
    }
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Talk with IRIS", fontFamily = Serif) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("IRIS listens until you stop, then answers aloud, even with the screen locked. What you say is " +
                    "sent to OpenAI to be written down, your words and IRIS's usual context go to the model to reply, " +
                    "and the reply is sent back to be spoken. Only the words are kept, as chat messages; the audio is not.")
                Text(cost)
            }
        },
        confirmButton = {
            Button(onClick = {
                val needed = buildList {
                    add(Manifest.permission.RECORD_AUDIO)
                    if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
                }.filter { ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED }
                if (needed.isEmpty()) onStart() else permissions.launch(needed.toTypedArray())
            }) { Text("Start talking") }
        },
        dismissButton = { TextButton(onClick = onCancel) { Text("Cancel") } },
    )
}

/** The conversation itself: the lens, what IRIS is doing, and its controls. */
@Composable
fun TalkPanel(onEnd: () -> Unit, onRetry: () -> Unit) {
    val colors = LocalIrisColors.current
    val state by TalkSession.state.collectAsState()
    val heard by TalkSession.level.collectAsState()
    val phase = state.phase
    // The lens follows the voice: the owner's as heard, IRIS's as a steady pulse.
    val pulse by rememberInfiniteTransition(label = "speaking").animateFloat(0f, 1f,
        infiniteRepeatable(tween(420), RepeatMode.Reverse), label = "speaking pulse")
    val target = when (phase) {
        TalkPhase.Hearing -> heard
        TalkPhase.Speaking -> 0.25f + pulse * 0.45f
        TalkPhase.Thinking -> 0.1f
        else -> 0f
    }
    val level by animateFloatAsState(target, tween(90), label = "lens level")
    Column(Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(132.dp), contentAlignment = Alignment.Center) {
            IrisOrb(104.dp, Modifier
                .graphicsLayer { scaleX = 1f + level * 0.18f; scaleY = 1f + level * 0.18f }
                .alpha(if (phase == TalkPhase.Paused || phase == TalkPhase.Error) 0.45f else 1f))
        }
        Text(says(phase), fontFamily = Serif, fontSize = 20.sp, color = colors.ink,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
        state.error?.let {
            Text(it, color = colors.rose, fontSize = 13.sp, textAlign = TextAlign.Center)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            when (phase) {
                TalkPhase.Error -> Button(onClick = onRetry) { Text("Try again") }
                TalkPhase.Paused -> OutlinedButton(onClick = TalkSession::resume) { Text("Resume listening") }
                else -> OutlinedButton(onClick = TalkSession::pause,
                    enabled = phase != TalkPhase.Starting && phase != TalkPhase.Thinking) { Text("Pause listening") }
            }
            if (phase == TalkPhase.Speaking) OutlinedButton(onClick = TalkSession::stopSpeaking) { Text("Stop speaking") }
            TextButton(onClick = onEnd) { Text("End") }
        }
        Text("Talk over IRIS to interrupt it.", color = colors.ink3, fontSize = 12.sp)
    }
}
