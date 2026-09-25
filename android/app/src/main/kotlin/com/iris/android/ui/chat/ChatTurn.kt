package com.iris.android.ui.chat

import com.iris.android.api.ChatStreamEvent

/** A reply is complete only after the server explicitly sends `done`. */
internal class ChatTurn {
    sealed interface Step {
        data class Append(val text: String) : Step
        data class Done(val messageId: String?) : Step
        data class Fail(val message: String, val saved: Boolean) : Step
    }

    private var finished = false

    fun accept(event: ChatStreamEvent): Step = when {
        event.error != null -> Step.Fail(event.error, event.saved ?: false)
        event.done == true -> {
            finished = true
            Step.Done(event.messageId)
        }
        else -> Step.Append(event.text ?: "")
    }

    fun end(): Step? = if (finished) null else Step.Fail("The reply was interrupted.", saved = true)
}
