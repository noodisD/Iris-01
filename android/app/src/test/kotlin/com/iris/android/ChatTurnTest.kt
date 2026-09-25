package com.iris.android

import com.iris.android.api.ChatStreamEvent
import com.iris.android.api.json
import com.iris.android.ui.chat.ChatTurn
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ChatTurnTest {
    private fun event(payload: String) = json.decodeFromString(ChatStreamEvent.serializer(), payload)

    @Test fun fragmentsRequireExplicitCompletion() {
        val turn = ChatTurn()
        assertEquals(ChatTurn.Step.Append("first "), turn.accept(event("""{"text":"first "}""")))
        assertEquals(ChatTurn.Step.Append("reply"), turn.accept(event("""{"text":"reply"}""")))
        assertEquals(ChatTurn.Step.Done("m1"), turn.accept(event("""{"done":true,"messageId":"m1"}""")))
        assertNull(turn.end())
    }

    @Test fun savedAndUnsavedErrorsStayDistinct() {
        assertEquals(ChatTurn.Step.Fail("boom", true),
            ChatTurn().accept(event("""{"error":"boom","saved":true}""")))
        assertEquals(ChatTurn.Step.Fail("boom", false),
            ChatTurn().accept(event("""{"error":"boom"}""")))
    }

    @Test fun droppedStreamCannotLookFinished() {
        val turn = ChatTurn()
        turn.accept(event("""{"text":"half a"}"""))
        assertEquals(ChatTurn.Step.Fail("The reply was interrupted.", true), turn.end())
    }
}
