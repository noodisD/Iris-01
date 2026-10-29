package com.iris.android.ui.journal

import com.iris.android.api.JournalEntry
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class EntryBodyTest {
    @Test fun aTurnsTimeReadsLikeTheWeb() {
        assertEquals("0:05", clock(5))
        assertEquals("12:40", clock(760))
        assertEquals("1:02:03", clock(3723))
    }

    @Test fun onlyTheOwnersAndUnclearTurnsAreMarked() {
        assertEquals(" (you)", roleNote("owner"))
        assertEquals("", roleNote("therapist"))
        assertEquals(" (speaker unclear)", roleNote("unclear"))
    }

    @Test fun anEntryReadsItsSessionAndEnglishVersionFromTheServer() {
        val json = Json { ignoreUnknownKeys = true }
        val entry = json.decodeFromString<JournalEntry>("""
            {"id":"1","userId":"1","lines":[],"text":"Zagrałam partię.","format":"session",
             "session":{"kind":"therapy","startedAt":"2026-03-02T18:00","turns":[{"at":5,"label":"Ania","role":"owner","text":"Zagrałam partię."}]},
             "translation":{"text":"I played a game.","from":"pl","session":{"turns":[{"at":5,"label":"Ania","role":"owner","text":"I played a game."}]}}}
        """)
        assertEquals("I played a game.", entry.translation!!.session!!.turns.single().text)
        assertEquals("Polish", languageName(entry.translation!!.from))
        assertNull(json.decodeFromString<JournalEntry>("""{"id":"2","userId":"1","lines":["x"]}""").translation)
    }
}
