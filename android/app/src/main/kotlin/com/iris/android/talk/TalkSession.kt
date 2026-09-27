package com.iris.android.talk

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaDataSource
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.os.PowerManager
import com.iris.android.api.ChatStreamEvent
import com.iris.android.api.Conversation
import com.iris.android.api.IrisLink
import com.iris.android.api.UploadPart
import com.iris.android.api.json
import com.iris.android.ui.chat.ChatTurn
import java.io.ByteArrayInputStream
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlin.coroutines.resume

/** What Chat shows of a spoken turn, as it happens. */
sealed interface TalkUpdate {
    val conversationId: String
    val turn: Int
    data class Heard(override val conversationId: String, override val turn: Int, val text: String) : TalkUpdate
    data class Fragment(override val conversationId: String, override val turn: Int, val text: String) : TalkUpdate
    data class Done(override val conversationId: String, override val turn: Int, val messageId: String?) : TalkUpdate
    data class Failed(override val conversationId: String, override val turn: Int, val message: String, val saved: Boolean) : TalkUpdate
}

@Serializable
private data class Heard(val text: String)

/**
 * A spoken conversation with IRIS (ADR-0025), kept outside any screen so it
 * carries on with the screen locked: TalkService holds it in the foreground.
 * Listen until the owner stops, transcribe, send through the ordinary chat
 * turn marked as spoken, speak the reply a sentence at a time, listen again.
 * The audio is never written anywhere; only its words reach IRIS's record.
 */
object TalkSession {
    private val _state = MutableStateFlow(TalkState())
    val state: StateFlow<TalkState> = _state
    private val _level = MutableStateFlow(0f)
    /** How loud the voice being heard is, 0 to 1, for the lens. */
    val level: StateFlow<Float> = _level
    private val _updates = MutableSharedFlow<TalkUpdate>(extraBufferCapacity = 256)
    val updates: SharedFlow<TalkUpdate> = _updates

    private var scope: CoroutineScope? = null
    private var conversationId: String? = null
    /** The conversation being spoken, so Chat can rejoin it after the screen was left. */
    var conversation: Conversation? = null
        private set
    private var speaker: Speaker? = null
    private var turnJob: Job? = null
    private var turn = 0
    private var active = -1
    @Volatile private var paused = false
    private var wakeLock: PowerManager.WakeLock? = null
    private var focus: AudioFocusRequest? = null

    private fun dispatch(event: TalkEvent) = _state.update { reduce(it, event) }

    val running: Boolean get() = scope != null

    @SuppressLint("MissingPermission")
    fun start(ctx: Context, open: Conversation) {
        if (scope != null) return
        val session = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        scope = session
        conversation = open
        conversationId = open.id
        paused = false
        dispatch(TalkEvent.Start)
        val audio = ctx.getSystemService(AudioManager::class.java)
        focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(SPEECH).build().also { audio.requestAudioFocus(it) }
        wakeLock = ctx.getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "iris:talk").apply { acquire(60 * 60 * 1000L) }
        speaker = Speaker(session,
            onStart = { dispatch(TalkEvent.ReplyStarted) },
            onDone = { dispatch(TalkEvent.Spoken) },
            onTrouble = { dispatch(TalkEvent.Trouble(it)) })
        session.launch(Dispatchers.IO) { listen() }
    }

    fun pause() {
        silence()
        paused = true
        dispatch(TalkEvent.Pause)
    }

    fun resume() {
        paused = false
        dispatch(TalkEvent.Resume)
    }

    fun stopSpeaking() {
        silence()
        dispatch(TalkEvent.StopSpeaking)
    }

    /** Ends the conversation. `error` keeps the reason on screen after the service stops. */
    fun end(ctx: Context, error: String? = null) {
        silence()
        scope?.cancel()
        scope = null
        speaker = null
        conversation = null
        conversationId = null
        focus?.let { ctx.getSystemService(AudioManager::class.java).abandonAudioFocusRequest(it) }
        focus = null
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
        _level.value = 0f
        if (error != null) dispatch(TalkEvent.Fail(error)) else dispatch(TalkEvent.End)
    }

    private fun silence() {
        active = -1
        speaker?.stop()
    }

    @SuppressLint("MissingPermission")
    private suspend fun listen() {
        val minBuffer = AudioRecord.getMinBufferSize(VoiceDetector.SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val recorder = try {
            // The voice-call input: echo-cancelled and noise-suppressed by the
            // phone, so IRIS's own voice from the speaker is mostly removed.
            AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, VoiceDetector.SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                maxOf(minBuffer, VoiceDetector.FRAME * 2 * 10))
        } catch (error: Exception) {
            dispatch(TalkEvent.Fail("The microphone could not be opened: ${error.message}"))
            return
        }
        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            recorder.release()
            dispatch(TalkEvent.Fail("IRIS needs the microphone. Allow it for IRIS in the phone's settings, then start again."))
            return
        }
        val echo = if (AcousticEchoCanceler.isAvailable()) AcousticEchoCanceler.create(recorder.audioSessionId)?.apply { enabled = true } else null
        val noise = if (NoiseSuppressor.isAvailable()) NoiseSuppressor.create(recorder.audioSessionId)?.apply { enabled = true } else null
        val detector = VoiceDetector()
        val frame = ShortArray(VoiceDetector.FRAME)
        // Frames left in which to stay strict after IRIS stops: the last echo
        // of its voice in the room is not the owner starting a turn.
        var afterSpeaking = 0
        try {
            recorder.startRecording()
            dispatch(TalkEvent.Ready)
            while (kotlinx.coroutines.currentCoroutineContext().isActive) {
                var read = 0
                while (read < frame.size) {
                    val n = recorder.read(frame, read, frame.size - read)
                    if (n < 0) throw IllegalStateException("The microphone stopped ($n).")
                    read += n
                }
                if (paused) { detector.reset(); continue }
                val phase = _state.value.phase
                if (phase == TalkPhase.Speaking) afterSpeaking = 50 else if (afterSpeaking > 0) afterSpeaking--
                detector.strict = phase == TalkPhase.Speaking || afterSpeaking > 0
                val event = detector.feed(frame)
                if (phase == TalkPhase.Hearing) _level.value = detector.level
                when (event) {
                    VoiceDetector.Event.Start -> when (phase) {
                        TalkPhase.Listening -> dispatch(TalkEvent.SpeechStart)
                        TalkPhase.Speaking -> { silence(); dispatch(TalkEvent.SpeechStart) }
                        else -> Unit  // IRIS is still thinking: turns never overlap
                    }
                    VoiceDetector.Event.Misfire -> { _level.value = 0f; dispatch(TalkEvent.Misfire) }
                    is VoiceDetector.Event.End -> { _level.value = 0f; scope?.launch { takeTurn(event.samples) } }
                    null -> Unit
                }
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            dispatch(TalkEvent.Fail(error.message ?: "The microphone stopped."))
        } finally {
            runCatching { recorder.stop() }
            echo?.release(); noise?.release()
            recorder.release()
        }
    }

    private suspend fun takeTurn(samples: ShortArray) {
        if (_state.value.phase != TalkPhase.Hearing) return
        dispatch(TalkEvent.SpeechEnd)
        val conversation = conversationId ?: return
        val text = try {
            val wav = encodeWav(samples)
            IrisLink.api().upload("/voice/transcribe",
                listOf(UploadPart("audio", "turn.wav", "audio/wav", null, { ByteArrayInputStream(wav) }, wav.size.toLong())),
                Heard.serializer()) {}.text.trim()
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            dispatch(TalkEvent.Trouble(error.message ?: "IRIS could not hear that."))
            return
        }
        if (text.isEmpty()) { dispatch(TalkEvent.HeardNothing); return }
        // A reply the owner talked over may still be arriving: turns never overlap.
        turnJob?.join()
        val id = ++turn
        active = id
        val voice = speaker ?: return
        voice.reset()
        _updates.emit(TalkUpdate.Heard(conversation, id, text))
        val splitter = SentenceSplitter()
        fun speak(sentences: List<String>) { if (active == id) sentences.forEach(voice::enqueue) }
        turnJob = scope?.launch {
            val chat = ChatTurn()
            val body = json.encodeToString(kotlinx.serialization.json.JsonObject.serializer(), buildJsonObject {
                put("text", JsonPrimitive(text))
                put("voice", JsonPrimitive(true))
            })
            try {
                var finished = false
                IrisLink.api().sse("/conversations/$conversation/messages/stream", body).collect { raw ->
                    if (finished) return@collect
                    when (val step = chat.accept(json.decodeFromJsonElement<ChatStreamEvent>(raw))) {
                        is ChatTurn.Step.Append -> {
                            _updates.emit(TalkUpdate.Fragment(conversation, id, step.text))
                            speak(splitter.push(step.text))
                        }
                        is ChatTurn.Step.Done -> {
                            finished = true
                            _updates.emit(TalkUpdate.Done(conversation, id, step.messageId))
                            speak(splitter.flush())
                            if (active == id) voice.finish()
                        }
                        is ChatTurn.Step.Fail -> throw ReplyFailed(step.message, step.saved)
                    }
                }
                if (!finished) throw ReplyFailed("The reply was interrupted.", true)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                val saved = (error as? ReplyFailed)?.saved ?: false
                _updates.emit(TalkUpdate.Failed(conversation, id, error.message ?: "IRIS could not reply.", saved))
                if (active == id) {
                    voice.stop()
                    dispatch(TalkEvent.Trouble(error.message ?: "IRIS could not reply."))
                }
            }
        }
    }

    private class ReplyFailed(override val message: String, val saved: Boolean) : Exception(message)

    private val SPEECH: AudioAttributes = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_ASSISTANT)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
        .build()

    /**
     * IRIS's voice: sentences are fetched as they arrive and played in order,
     * the first while the rest of the reply is still being written. `stop`
     * silences it at once, for when the owner talks over IRIS.
     */
    private class Speaker(
        private val scope: CoroutineScope,
        private val onStart: () -> Unit,
        private val onDone: () -> Unit,
        private val onTrouble: (String) -> Unit,
    ) {
        private var queue = Channel<Deferred<ByteArray?>>(Channel.UNLIMITED)
        private var player: Job? = null
        private val fetches = mutableListOf<Deferred<ByteArray?>>()

        fun reset() {
            stop()
            queue = Channel(Channel.UNLIMITED)
            val current = queue
            player = scope.launch {
                var started = false
                for (next in current) {
                    val bytes = next.await() ?: continue
                    if (!started) { started = true; onStart() }
                    play(bytes)
                }
                onDone()
            }
        }

        fun enqueue(sentence: String) {
            val body = json.encodeToString(kotlinx.serialization.json.JsonObject.serializer(),
                buildJsonObject { put("text", JsonPrimitive(sentence)) })
            val audio = scope.async(Dispatchers.IO) {
                try {
                    IrisLink.api().postForBytes("/voice/speech", body, "audio/mpeg")
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (error: Exception) {
                    onTrouble(error.message ?: "IRIS could not speak that.")
                    null
                }
            }
            synchronized(fetches) { fetches += audio }
            queue.trySend(audio)
        }

        /** The reply is complete: once the queue empties, IRIS is done speaking. */
        fun finish() { queue.close() }

        fun stop() {
            player?.cancel()
            player = null
            queue.close()
            synchronized(fetches) { fetches.forEach { it.cancel() }; fetches.clear() }
        }

        private suspend fun play(bytes: ByteArray) = withContext(Dispatchers.Main) {
            suspendCancellableCoroutine { done ->
                val media = MediaPlayer()
                val finish = {
                    runCatching { media.release() }
                    if (done.isActive) done.resume(Unit)
                }
                done.invokeOnCancellation { runCatching { media.stop() }; runCatching { media.release() } }
                try {
                    media.setAudioAttributes(SPEECH)
                    media.setDataSource(Bytes(bytes))
                    media.setOnCompletionListener { finish() }
                    media.setOnErrorListener { _, _, _ -> finish(); true }
                    media.prepare()
                    media.start()
                } catch (error: Exception) {
                    finish()
                }
            }
        }
    }

    private class Bytes(private val data: ByteArray) : MediaDataSource() {
        override fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int {
            if (position >= data.size) return -1
            val count = minOf(size, data.size - position.toInt())
            System.arraycopy(data, position.toInt(), buffer, offset, count)
            return count
        }
        override fun getSize(): Long = data.size.toLong()
        override fun close() = Unit
    }
}
