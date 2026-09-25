package com.iris.android.ui.chat

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.iris.android.api.ChatMessage
import com.iris.android.api.ChatStreamEvent
import com.iris.android.api.Conversation
import com.iris.android.api.IrisLink
import com.iris.android.api.User
import com.iris.android.api.json
import com.iris.android.ui.Loadable
import java.time.Instant
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.decodeFromJsonElement

class ChatViewModel(savedStateHandle: SavedStateHandle) : ViewModel() {
    private val _conversation = MutableStateFlow<Loadable<Conversation>>(Loadable.Loading)
    val conversation: StateFlow<Loadable<Conversation>> = _conversation
    private val _messages = MutableStateFlow<List<ChatMessage>>(emptyList())
    val messages: StateFlow<List<ChatMessage>> = _messages
    private val _user = MutableStateFlow<User?>(null)
    val user: StateFlow<User?> = _user
    private val _draft = MutableStateFlow(savedStateHandle.get<String>("draft").orEmpty())
    val draft: StateFlow<String> = _draft
    private val _pending = MutableStateFlow(false)
    val pending: StateFlow<Boolean> = _pending
    private val _failure = MutableStateFlow<String?>(null)
    val failure: StateFlow<String?> = _failure
    private var draftInitialized = _draft.value.isNotEmpty()
    private var visitOpen = false
    private var generation = 0

    /** Nav arguments are offered for editing, never sent automatically. */
    fun setInitialDraft(text: String?) {
        if (!draftInitialized && text != null) {
            draftInitialized = true
            if (_draft.value.isEmpty()) _draft.value = text
        }
    }

    fun setDraft(text: String) { _draft.value = text }

    /** A tab return starts an empty open. Rotation keeps the one already started. */
    fun onScreenEntered() {
        if (visitOpen) return
        visitOpen = true
        startSession()
    }

    fun onScreenLeft(configurationChange: Boolean) {
        if (!configurationChange) visitOpen = false
    }

    fun startSession() {
        val gen = ++generation
        _pending.value = false
        _failure.value = null
        _messages.value = emptyList()
        _conversation.value = Loadable.Loading
        viewModelScope.launch {
            launch {
                try {
                    val loaded = IrisLink.api().send("GET", "/user", null, User.serializer())
                    if (gen == generation) _user.value = loaded
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: Exception) {
                    // The web shows the conversation even when the optional day tag cannot load.
                }
            }
            try {
                val opened = IrisLink.api().send("POST", "/conversations", null, Conversation.serializer())
                if (gen != generation) return@launch
                _conversation.value = Loadable.Ready(opened)
                _messages.value = emptyList()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (gen == generation) _conversation.value = Loadable.Failed(error.message ?: error.toString())
            }
        }
    }

    private suspend fun fetchMessages(id: String) {
        _messages.value = IrisLink.api().send("GET", "/conversations/$id/messages", null,
            ListSerializer(ChatMessage.serializer()))
    }

    fun send() {
        val gen = generation
        val text = _draft.value.trim()
        val current = (_conversation.value as? Loadable.Ready)?.value ?: return
        if (text.isEmpty() || _pending.value) return
        _pending.value = true
        _draft.value = ""
        _failure.value = null
        val now = Instant.now()
        val ownerId = "m_${now.toEpochMilli()}"
        val replyId = "m_stream_${now.toEpochMilli()}"
        _messages.value += listOf(
            ChatMessage(ownerId, current.id, "user", text, now.toString()),
            ChatMessage(replyId, current.id, "iris", "", now.toString(), streaming = true),
        )
        viewModelScope.launch {
            if (gen != generation) return@launch
            try {
                val turn = ChatTurn()
                var terminal: ChatTurn.Step? = null
                val body = json.encodeToString(kotlinx.serialization.json.JsonObject.serializer(),
                    kotlinx.serialization.json.buildJsonObject { put("text", kotlinx.serialization.json.JsonPrimitive(text)) })
                IrisLink.api().sse("/conversations/${current.id}/messages/stream", body)
                    .map { turn.accept(json.decodeFromJsonElement<ChatStreamEvent>(it)) }
                    .takeWhile { step ->
                        if (step is ChatTurn.Step.Append) true else {
                            terminal = step
                            false
                        }
                    }
                    .collect { step ->
                        if (step is ChatTurn.Step.Append) {
                            if (gen != generation) return@collect
                            _messages.value = _messages.value.map { message ->
                                if (message.id == replyId) message.copy(text = message.text + step.text) else message
                            }
                        }
                    }
                if (gen != generation) return@launch
                when (val last = terminal ?: turn.end()) {
                    is ChatTurn.Step.Done -> {
                        _messages.value = _messages.value.map { message ->
                            if (message.id == replyId) message.copy(id = last.messageId ?: replyId, streaming = false)
                            else message
                        }
                    }
                    is ChatTurn.Step.Fail -> throw ReplyFailed(last.message, last.saved)
                    else -> Unit
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (gen != generation) return@launch
                _messages.value = _messages.value.filterNot { it.id == replyId || it.id == ownerId }
                try {
                    fetchMessages(current.id)
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: Exception) {
                    // Keep the reconciled local list if the history is temporarily unreachable.
                }
                val saved = error is ReplyFailed && error.saved
                if (!saved && _draft.value.isEmpty()) _draft.value = text
                val reason = error.message ?: error.toString()
                _failure.value = if (saved) "Your message was saved, but Iris couldn't reply: $reason"
                    else "Couldn't reach Iris: $reason"
            } finally {
                if (gen == generation) _pending.value = false
            }
        }
    }

    private class ReplyFailed(override val message: String, val saved: Boolean) : Exception(message)
}
