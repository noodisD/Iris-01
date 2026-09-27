package com.iris.android.talk

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.log10
import kotlin.math.sqrt

/*
 * Talk mode's logic, free of Android so it can be tested (ADR-0025): the
 * turn-taking rules, the splitting of a streamed reply into sentences IRIS can
 * speak one at a time, voice detection on microphone frames, and the WAV
 * encoding of what the owner said. The web app's lib/talk.ts is the same logic.
 */

enum class TalkPhase { Off, Starting, Listening, Hearing, Thinking, Speaking, Paused, Error }

data class TalkState(val phase: TalkPhase = TalkPhase.Off, val error: String? = null)

sealed interface TalkEvent {
    data object Start : TalkEvent
    data object Ready : TalkEvent
    data object SpeechStart : TalkEvent
    data object SpeechEnd : TalkEvent
    data object Misfire : TalkEvent
    data object HeardNothing : TalkEvent
    data object ReplyStarted : TalkEvent
    data object Spoken : TalkEvent
    data object StopSpeaking : TalkEvent
    data object Pause : TalkEvent
    data object Resume : TalkEvent
    data class Trouble(val message: String) : TalkEvent
    data class Fail(val message: String) : TalkEvent
    data object End : TalkEvent
}

/**
 * What happens next. Anything not listed for a phase is ignored, which is how
 * the owner's voice is not taken as a new turn while IRIS is still thinking
 * about the last one: turns never overlap.
 */
fun reduce(state: TalkState, event: TalkEvent): TalkState {
    if (event is TalkEvent.End) return TalkState()
    if (event is TalkEvent.Fail) return TalkState(TalkPhase.Error, event.message)
    fun to(phase: TalkPhase, error: String? = null) = TalkState(phase, error)
    return when (state.phase) {
        TalkPhase.Off, TalkPhase.Error -> if (event is TalkEvent.Start) to(TalkPhase.Starting) else state
        TalkPhase.Starting -> if (event is TalkEvent.Ready) to(TalkPhase.Listening) else state
        TalkPhase.Listening -> when (event) {
            TalkEvent.SpeechStart -> to(TalkPhase.Hearing)
            TalkEvent.Pause -> to(TalkPhase.Paused)
            else -> state
        }
        TalkPhase.Hearing -> when (event) {
            TalkEvent.SpeechEnd -> to(TalkPhase.Thinking)
            TalkEvent.Misfire -> to(TalkPhase.Listening, state.error)
            TalkEvent.Pause -> to(TalkPhase.Paused)
            else -> state
        }
        TalkPhase.Thinking -> when (event) {
            TalkEvent.ReplyStarted -> to(TalkPhase.Speaking)
            TalkEvent.HeardNothing, TalkEvent.Spoken -> to(TalkPhase.Listening)
            is TalkEvent.Trouble -> to(TalkPhase.Listening, event.message)
            else -> state
        }
        // Talking over IRIS stops it and takes the turn.
        TalkPhase.Speaking -> when (event) {
            TalkEvent.SpeechStart -> to(TalkPhase.Hearing)
            TalkEvent.Spoken, TalkEvent.StopSpeaking -> to(TalkPhase.Listening)
            TalkEvent.Pause -> to(TalkPhase.Paused)
            is TalkEvent.Trouble -> to(TalkPhase.Listening, event.message)
            else -> state
        }
        TalkPhase.Paused -> if (event is TalkEvent.Resume) to(TalkPhase.Listening) else state
    }
}

private val ABBREVIATIONS = setOf("e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "st", "no", "approx", "cf", "p.s")
private const val MAX_SPOKEN = 500
private val SENTENCE_END = Regex("""([.!?…]+)(["'”’)]*)(\s+)|\n+""")

/** What IRIS would read aloud: markdown and link syntax are not words. */
fun speakable(text: String): String = text
    .replace(Regex("""\[([^\]]+)]\([^)]*\)"""), "$1")
    .replace(Regex("""[*_`#>]+"""), "")
    .replace(Regex("""(?m)^\s*[-•]\s+"""), "")
    .replace(Regex("""\s+"""), " ")
    .trim()

private fun splitLong(sentence: String): List<String> {
    val out = mutableListOf<String>()
    var rest = sentence
    while (rest.length > MAX_SPOKEN) {
        val window = rest.substring(0, MAX_SPOKEN)
        val cut = maxOf(window.lastIndexOf(", "), window.lastIndexOf("; "), window.lastIndexOf(' '))
        val at = if (cut > 0) cut + 1 else MAX_SPOKEN
        out += rest.substring(0, at).trim()
        rest = rest.substring(at).trim()
    }
    if (rest.isNotEmpty()) out += rest
    return out
}

/**
 * Splits a reply streamed in fragments into sentences as soon as each is
 * complete, so IRIS can start speaking the first while the rest is written.
 */
class SentenceSplitter {
    private var buffer = ""

    fun push(fragment: String): List<String> {
        buffer += fragment
        val out = mutableListOf<String>()
        var start = 0
        for (match in SENTENCE_END.findAll(buffer)) {
            val punctuation = match.groupValues[1]
            val end = if (punctuation.isNotEmpty()) match.range.first + punctuation.length + match.groupValues[2].length
                else match.range.first
            val candidate = buffer.substring(start, end)
            if (punctuation == "." && isAbbreviation(candidate)) continue
            val sentence = speakable(candidate)
            if (sentence.isNotEmpty()) out += splitLong(sentence)
            start = match.range.last + 1
        }
        buffer = buffer.substring(start)
        return out
    }

    fun flush(): List<String> {
        val rest = speakable(buffer)
        buffer = ""
        return if (rest.isEmpty()) emptyList() else splitLong(rest)
    }

    private fun isAbbreviation(candidate: String): Boolean {
        val word = candidate.dropLast(1).split(Regex("""\s+""")).lastOrNull()?.lowercase().orEmpty()
        return word in ABBREVIATIONS || Regex("^[a-z]$").matches(word)
    }
}

/**
 * Voice detection on 20 ms frames of 16 kHz speech: a frame is speech when it
 * is clearly louder than a noise floor that adapts to the room. The microphone
 * is the phone's voice-call input, already echo-cancelled and noise-suppressed,
 * which is what makes loudness a fair signal. While IRIS speaks the detector is
 * stricter, so IRIS's own voice leaking past echo cancellation is not taken
 * for the owner talking over it.
 */
class VoiceDetector(
    private val marginDb: Double = 12.0,
    private val strictMarginDb: Double = 20.0,
    private val startFrames: Int = 6,          // 120 ms of speech to begin
    private val strictStartFrames: Int = 15,   // 300 ms while IRIS speaks
    private val endFrames: Int = 45,           // 900 ms of quiet ends the turn
    private val minSpeechFrames: Int = 25,     // under 500 ms is a cough, not a turn
    private val calibrationFrames: Int = 25,   // 500 ms to learn the room before listening
    private val tailFrames: Int = 10,          // 200 ms of the quiet kept after speech
    private val padFrames: Int = 15,           // 300 ms kept from before the start
    private val maxFrames: Int = 50 * 60,      // one minute at most per turn
) {
    sealed interface Event {
        data object Start : Event
        data class End(val samples: ShortArray) : Event
        data object Misfire : Event
    }

    /** Stricter while IRIS is speaking. */
    var strict = false

    /** How loud the last frame was, 0 to 1, for the lens. */
    var level = 0f
        private set

    private var floor = -60.0
    private var calibrated = 0
    private var run = 0
    private var quiet = 0
    private var speechCount = 0
    private var speaking = false
    private val before = ArrayDeque<ShortArray>()
    private val turn = mutableListOf<ShortArray>()

    fun reset() {
        run = 0; quiet = 0; speechCount = 0; speaking = false
        before.clear(); turn.clear()
    }

    fun feed(frame: ShortArray): Event? {
        val db = decibels(frame)
        // The room first. The floor used to start at -60 dB and rise slowly,
        // so in a room louder than that the first moments read as speech and
        // a turn of nothing but room noise was sent, which the transcriber
        // turned into invented words.
        if (calibrated < calibrationFrames) {
            floor = if (calibrated == 0) db else floor * 0.8 + db * 0.2
            floor = floor.coerceIn(-75.0, -30.0)
            calibrated++
            level = 0f
            return null
        }
        level = ((db - floor) / 30.0).coerceIn(0.0, 1.0).toFloat()
        val loud = db > floor + (if (strict) strictMarginDb else marginDb) && db > -50.0
        if (!speaking) {
            // The floor follows the room down quickly and up slowly, and only
            // while nobody is speaking.
            floor = if (db < floor) floor * 0.7 + db * 0.3 else floor + (db - floor) * 0.02
            floor = floor.coerceIn(-75.0, -30.0)
            before.addLast(frame)
            if (before.size > padFrames) before.removeFirst()
            run = if (loud) run + 1 else 0
            if (run >= (if (strict) strictStartFrames else startFrames)) {
                speaking = true
                turn.clear(); turn.addAll(before); before.clear()
                speechCount = run; quiet = 0
                return Event.Start
            }
            return null
        }
        turn += frame
        if (loud) { speechCount++; quiet = 0 } else quiet++
        if (quiet >= endFrames || turn.size >= maxFrames) {
            val enough = speechCount >= minSpeechFrames
            // Long silence at the end is where transcribers invent words.
            val kept = if (quiet > tailFrames) turn.dropLast(quiet - tailFrames) else turn
            val samples = if (enough) join(kept) else null
            reset()
            return if (samples != null) Event.End(samples) else Event.Misfire
        }
        return null
    }

    private fun join(frames: List<ShortArray>): ShortArray {
        val out = ShortArray(frames.sumOf { it.size })
        var at = 0
        for (f in frames) { f.copyInto(out, at); at += f.size }
        return out
    }

    companion object {
        const val SAMPLE_RATE = 16000
        const val FRAME = SAMPLE_RATE / 50

        fun decibels(frame: ShortArray): Double {
            if (frame.isEmpty()) return -90.0
            var sum = 0.0
            for (s in frame) { val v = s / 32768.0; sum += v * v }
            val rms = sqrt(sum / frame.size)
            return if (rms <= 1e-6) -90.0 else 20 * log10(rms)
        }
    }
}

/** 16 kHz mono 16-bit samples as a WAV file. */
fun encodeWav(samples: ShortArray, sampleRate: Int = VoiceDetector.SAMPLE_RATE): ByteArray {
    val buffer = ByteBuffer.allocate(44 + samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
    buffer.put("RIFF".toByteArray()).putInt(36 + samples.size * 2).put("WAVE".toByteArray())
    buffer.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
        .putInt(sampleRate).putInt(sampleRate * 2).putShort(2).putShort(16)
    buffer.put("data".toByteArray()).putInt(samples.size * 2)
    for (s in samples) buffer.putShort(s)
    return buffer.array()
}
