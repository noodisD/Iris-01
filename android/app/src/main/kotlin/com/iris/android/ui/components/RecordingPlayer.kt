package com.iris.android.ui.components

import android.media.MediaPlayer
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iris.android.R
import com.iris.android.api.IrisLink
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Mono
import java.io.File
import java.security.MessageDigest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

sealed interface RecordingSource {
    data class Remote(val serverPath: String, val cacheKey: String) : RecordingSource
    data class Local(val file: File) : RecordingSource
}

/** Playback ownership spans both the journal and the voice-import review. */
private object RecordingFocus {
    var active: Playback? = null
        private set

    fun acquire(player: Playback) {
        if (active !== player) active?.pause()
        active = player
    }

    fun release(player: Playback) {
        if (active === player) active = null
    }
}

private class Playback {
    var player: MediaPlayer? = null
        private set
    var playing by mutableStateOf(false)
        private set
    var loading by mutableStateOf(false)
    var positionMs by mutableIntStateOf(0)
        private set
    var durationMs by mutableIntStateOf(0)
        private set
    var error by mutableStateOf<String?>(null)
    var disposed = false
        private set

    fun pause() {
        player?.let { if (playing) it.pause() }
        playing = false
        RecordingFocus.release(this)
    }

    fun start() {
        val media = player ?: return
        RecordingFocus.acquire(this)
        media.start()
        playing = true
    }

    fun install(media: MediaPlayer) {
        if (disposed) {
            media.release()
            return
        }
        player = media
        durationMs = media.duration.coerceAtLeast(0)
        media.setOnCompletionListener {
            playing = false
            positionMs = durationMs
            RecordingFocus.release(this)
        }
        media.setOnErrorListener { _, _, _ ->
            playing = false
            error = "The recording could not be played."
            RecordingFocus.release(this)
            true
        }
        start()
    }

    fun tick() {
        if (playing) try {
            positionMs = player?.currentPosition ?: 0
        } catch (_: IllegalStateException) {
            playing = false
        }
    }

    fun dispose() {
        disposed = true
        RecordingFocus.release(this)
        playing = false
        player?.release()
        player = null
    }
}

private fun clock(millis: Int): String {
    val seconds = millis.coerceAtLeast(0) / 1000
    return "${seconds / 60}:${(seconds % 60).toString().padStart(2, '0')}"
}

@Composable
fun RecordingPlayer(source: RecordingSource) {
    val colors = LocalIrisColors.current
    val context = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    val playback = remember(source) { Playback() }
    DisposableEffect(playback) { onDispose { playback.dispose() } }
    LaunchedEffect(playback, playback.playing) {
        while (playback.playing) {
            playback.tick()
            delay(250)
        }
    }

    Column(Modifier.fillMaxWidth().semantics { contentDescription = "the recording this was transcribed from" }) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = {
                if (playback.playing) {
                    playback.pause()
                } else if (!playback.loading) {
                    if (playback.player != null) playback.start()
                    else scope.launch {
                        playback.loading = true
                        playback.error = null
                        var prepared: MediaPlayer? = null
                        try {
                            val file = when (source) {
                                is RecordingSource.Local -> source.file
                                is RecordingSource.Remote -> {
                                    val key = MessageDigest.getInstance("SHA-256")
                                        .digest(source.cacheKey.toByteArray(Charsets.UTF_8))
                                        .joinToString("") { "%02x".format(it) }
                                    val target = File(context.cacheDir, "recordings/$key")
                                    if (!target.isFile) IrisLink.api().download(source.serverPath, target)
                                    target
                                }
                            }
                            withContext(Dispatchers.IO) {
                                MediaPlayer().apply {
                                    prepared = this
                                    setDataSource(file.absolutePath)
                                    prepare()
                                }
                            }
                            playback.install(prepared!!)
                            prepared = null
                        } catch (cancelled: CancellationException) {
                            throw cancelled
                        } catch (error: Exception) {
                            if (!playback.disposed) playback.error = error.message ?: "The recording could not be played."
                        } finally {
                            playback.loading = false
                            prepared?.release()
                        }
                    }
                }
            }, enabled = !playback.loading) {
                if (playback.loading) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                else Icon(painterResource(if (playback.playing) R.drawable.ic_pause else R.drawable.ic_play_arrow),
                    contentDescription = if (playback.playing) "Pause recording" else "Play recording")
            }
            LinearProgressIndicator(
                progress = if (playback.durationMs > 0) playback.positionMs.toFloat() / playback.durationMs else 0f,
                modifier = Modifier.weight(1f), color = colors.sage, trackColor = colors.line,
            )
            Text("${clock(playback.positionMs)} / ${clock(playback.durationMs)}", fontFamily = Mono,
                fontSize = 11.sp, color = colors.ink3)
        }
        playback.error?.let { Text(it, fontFamily = Mono, fontSize = 12.sp, color = colors.rose) }
    }
}
