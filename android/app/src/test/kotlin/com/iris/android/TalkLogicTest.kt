package com.iris.android

import com.iris.android.talk.SentenceSplitter
import com.iris.android.talk.TalkEvent
import com.iris.android.talk.TalkPhase
import com.iris.android.talk.TalkState
import com.iris.android.talk.VoiceDetector
import com.iris.android.talk.encodeWav
import com.iris.android.talk.reduce
import com.iris.android.talk.speakable
import kotlin.math.PI
import kotlin.math.sin
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TalkLogicTest {
    private fun run(events: List<TalkEvent>, from: TalkState = TalkState()) = events.fold(from, ::reduce)

    @Test
    fun listensHearsThinksSpeaksAndListensAgain() {
        val phases = mutableListOf<TalkPhase>()
        listOf(TalkEvent.Start, TalkEvent.Ready, TalkEvent.SpeechStart, TalkEvent.SpeechEnd,
            TalkEvent.ReplyStarted, TalkEvent.Spoken).fold(TalkState()) { state, event ->
            reduce(state, event).also { phases += it.phase }
        }
        assertEquals(listOf(TalkPhase.Starting, TalkPhase.Listening, TalkPhase.Hearing, TalkPhase.Thinking,
            TalkPhase.Speaking, TalkPhase.Listening), phases)
    }

    @Test
    fun talkingOverIrisTakesTheTurnButNotWhileItThinks() {
        val thinking = run(listOf(TalkEvent.Start, TalkEvent.Ready, TalkEvent.SpeechStart, TalkEvent.SpeechEnd))
        assertEquals(thinking, reduce(thinking, TalkEvent.SpeechStart))
        val speaking = reduce(thinking, TalkEvent.ReplyStarted)
        assertEquals(TalkPhase.Hearing, reduce(speaking, TalkEvent.SpeechStart).phase)
    }

    @Test
    fun troublePauseFailAndEnd() {
        val thinking = run(listOf(TalkEvent.Start, TalkEvent.Ready, TalkEvent.SpeechStart, TalkEvent.SpeechEnd))
        assertEquals(TalkState(TalkPhase.Listening, "IRIS could not hear that."),
            reduce(thinking, TalkEvent.Trouble("IRIS could not hear that.")))
        val listening = run(listOf(TalkEvent.Start, TalkEvent.Ready))
        assertEquals(TalkPhase.Paused, run(listOf(TalkEvent.Pause, TalkEvent.SpeechStart), listening).phase)
        assertEquals(TalkPhase.Listening, run(listOf(TalkEvent.Pause, TalkEvent.Resume), listening).phase)
        assertEquals(TalkState(TalkPhase.Error, "No microphone."), reduce(listening, TalkEvent.Fail("No microphone.")))
        assertEquals(TalkState(), reduce(listening, TalkEvent.End))
    }

    @Test
    fun speaksEachSentenceAsSoonAsItIsComplete() {
        val splitter = SentenceSplitter()
        assertEquals(emptyList<String>(), splitter.push("Beans would do "))
        assertEquals(listOf("Beans would do well there."), splitter.push("well there. They like "))
        assertEquals(listOf("They like sun!"), splitter.push("sun! Would you"))
        assertEquals(listOf("Would you"), splitter.flush())
    }

    @Test
    fun abbreviationsInitialsAndDecimalsDoNotEndASentence() {
        val out = SentenceSplitter().push("Try hardy plants, e.g. kale or chard. Mr. Lee grew 3.5 kg of it. J. R. said so. ")
        assertEquals(listOf("Try hardy plants, e.g. kale or chard.", "Mr. Lee grew 3.5 kg of it.", "J. R. said so."), out)
    }

    @Test
    fun readsNoMarkdownAloud() {
        assertEquals("Water the beds at dusk.", speakable("**Water** the [beds](http://x) at `dusk`."))
    }

    private fun silence() = ShortArray(VoiceDetector.FRAME) { ((it % 7) - 3).toShort() }
    private fun voice(amplitude: Double = 6000.0) =
        ShortArray(VoiceDetector.FRAME) { (amplitude * sin(2 * PI * 220 * it / VoiceDetector.SAMPLE_RATE)).toInt().toShort() }

    private fun feed(detector: VoiceDetector, frames: List<ShortArray>) = frames.mapNotNull { detector.feed(it) }

    @Test
    fun aSpokenTurnStartsAndEndsWithTheQuietAfterIt() {
        val detector = VoiceDetector()
        val events = feed(detector, List(50) { silence() } + List(60) { voice() } + List(50) { silence() })
        assertEquals(VoiceDetector.Event.Start, events[0])
        val end = events[1] as VoiceDetector.Event.End
        // The turn includes the speech, a little from before it, and the quiet that ended it.
        assertTrue(end.samples.size >= 60 * VoiceDetector.FRAME)
        assertEquals(2, events.size)
    }

    @Test
    fun aShortSoundIsAMisfireNotATurn() {
        val detector = VoiceDetector()
        val events = feed(detector, List(50) { silence() } + List(8) { voice() } + List(50) { silence() })
        assertEquals(listOf(VoiceDetector.Event.Start, VoiceDetector.Event.Misfire), events)
    }

    @Test
    fun steadyQuietNeverStartsATurn() {
        assertNull(feed(VoiceDetector(), List(500) { silence() }).firstOrNull())
    }

    @Test
    fun whileIrisSpeaksAQuieterVoiceDoesNotInterrupt() {
        val relaxed = VoiceDetector()
        val strict = VoiceDetector().apply { this.strict = true }
        // A room at about -60 dB, and a voice at about -45 dB: clear of the room,
        // but not by the margin needed to talk over IRIS.
        val room = List(80) { ShortArray(VoiceDetector.FRAME) { i -> (if (i % 2 == 0) 30 else -30).toShort() } }
        val quietVoice = room + List(30) { voice(amplitude = 250.0) }
        assertEquals(VoiceDetector.Event.Start, feed(relaxed, quietVoice).firstOrNull())
        assertNull(feed(strict, quietVoice).firstOrNull())
        assertEquals(VoiceDetector.Event.Start, feed(strict, List(30) { voice() }).firstOrNull())
    }

    @Test
    fun whatWasSaidIsA16kMonoWav() {
        val wav = encodeWav(ShortArray(16000))
        assertEquals(44 + 32000, wav.size)
        assertEquals("RIFF", String(wav, 0, 4))
        assertEquals("WAVE", String(wav, 8, 4))
    }
}
