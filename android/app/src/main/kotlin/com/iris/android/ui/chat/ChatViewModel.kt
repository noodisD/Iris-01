package com.iris.android.ui.chat

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.iris.android.api.ChatMessage
import com.iris.android.api.ChatStreamEvent
import com.iris.android.api.DiscussionPreview
import com.iris.android.api.EvidenceRef
import com.iris.android.api.Conversation
import com.iris.android.api.IrisLink
import com.iris.android.api.User
import com.iris.android.api.valid
import com.iris.android.api.json
import com.iris.android.talk.TalkSession
import com.iris.android.talk.TalkUpdate
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

class ChatViewModel(private val savedStateHandle: SavedStateHandle) : ViewModel() {
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
    private val _reference = MutableStateFlow<EvidenceRef?>(
        savedStateHandle.get<String>("selectedEvidence")?.takeIf { it.isNotEmpty() }
            ?.let { runCatching { json.decodeFromString(EvidenceRef.serializer(), it) }.getOrNull() })
    val reference: StateFlow<EvidenceRef?> = _reference
    private val _preview = MutableStateFlow<Loadable<DiscussionPreview>?>(null)
    val preview: StateFlow<Loadable<DiscussionPreview>?> = _preview
    private var draftInitialized = _draft.value.isNotEmpty()
    private var evidenceInitialized = savedStateHandle.contains("selectedEvidence")
    private var attachedToTalk = false

    init {
        // A spoken turn (ADR-0025) is shown as it happens, like a typed one.
        viewModelScope.launch { TalkSession.updates.collect(::onSpoken) }
        _reference.value?.let(::loadEvidence)
    }

    private fun onSpoken(update: TalkUpdate) {
        val current = (_conversation.value as? Loadable.Ready)?.value ?: return
        if (update.conversationId != current.id) return
        val replyId = "m_talk_reply_${update.turn}"
        when (update) {
            is TalkUpdate.Heard -> {
                val now = Instant.now().toString()
                _failure.value = null
                _messages.value += listOf(
                    ChatMessage("m_talk_${update.turn}", current.id, "user", update.text, now),
                    ChatMessage(replyId, current.id, "iris", "", now, streaming = true),
                )
            }
            is TalkUpdate.Fragment -> _messages.value = _messages.value.map { message ->
                if (message.id == replyId) message.copy(text = message.text + update.text) else message
            }
            is TalkUpdate.Done -> _messages.value = _messages.value.map { message ->
                if (message.id == replyId) message.copy(id = update.messageId ?: replyId, streaming = false) else message
            }
            is TalkUpdate.Failed -> {
                _messages.value = _messages.value.filterNot { it.id == replyId }
                viewModelScope.launch {
                    try { fetchMessages(current.id) } catch (cancelled: CancellationException) { throw cancelled } catch (e: Exception) { com.iris.android.telemetry.Telemetry.error("ChatViewModel.onSpoken", e) }
                }
            }
        }
    }
    private var visitOpen = false
    private var generation = 0

    /** Navigation carries only a typed pointer; the current owner evidence is loaded before sending. */
    fun setEvidence(ref: EvidenceRef?, invalid: Boolean = false) {
        if (evidenceInitialized || (!invalid && ref == null)) return
        evidenceInitialized = true
        if (ref == null || !ref.valid()) {
            _preview.value = Loadable.Failed("That evidence link is invalid.")
            return
        }
        _reference.value = ref
        savedStateHandle["selectedEvidence"] = json.encodeToString(EvidenceRef.serializer(), ref)
        attachedToTalk = TalkSession.conversation != null
        loadEvidence(ref)
    }

    private fun loadEvidence(ref: EvidenceRef) {
        _preview.value = Loadable.Loading
        viewModelScope.launch {
            try {
                val path = "/discovery/discussion?ref=" +
                    java.net.URLEncoder.encode(json.encodeToString(EvidenceRef.serializer(), ref), Charsets.UTF_8)
                val loaded = IrisLink.api().send("GET", path, null, DiscussionPreview.serializer())
                if (_reference.value != ref) return@launch
                _preview.value = Loadable.Ready(loaded)
                if (!draftInitialized && _draft.value.isEmpty()) {
                    draftInitialized = true
                    setDraft(loaded.question)
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (_reference.value == ref) _preview.value =
                    Loadable.Failed(error.message ?: "Selected evidence is unavailable.")
            }
        }
    }

    fun retryEvidence() { _reference.value?.let(::loadEvidence) }
    fun acceptUpdatedEvidence() {
        val loaded = (_preview.value as? Loadable.Ready)?.value ?: return
        _reference.value = loaded.ref
        savedStateHandle["selectedEvidence"] = json.encodeToString(EvidenceRef.serializer(), loaded.ref)
        _preview.value = Loadable.Ready(loaded.copy(changed = false))
    }
    fun removeEvidence() {
        _reference.value = null
        savedStateHandle["selectedEvidence"] = ""
        _preview.value = null
    }
    fun setDraft(text: String) {
        draftInitialized = true
        _draft.value = text
        savedStateHandle["draft"] = text
    }

    /** A tab return starts an empty open. Rotation keeps the one already started. */
    fun onTalkStateChanged() {
        if (attachedToTalk && _reference.value != null &&
            TalkSession.conversation == null && !TalkSession.running) {
            attachedToTalk = false
            startSession()
        }
    }

    fun onScreenEntered() {
        if (visitOpen) return
        visitOpen = true
        startSession()
    }

    fun onScreenLeft(configurationChange: Boolean) {
        if (!configurationChange) visitOpen = false
    }

    fun startSession() {
        // A conversation still being spoken is rejoined, not replaced: the
        // screen may have been left while IRIS kept listening.
        TalkSession.conversation?.let { spoken ->
            ++generation
            _pending.value = false
            _failure.value = null
            _conversation.value = Loadable.Ready(spoken)
            viewModelScope.launch {
                try { fetchMessages(spoken.id) } catch (cancelled: CancellationException) { throw cancelled } catch (e: Exception) { com.iris.android.telemetry.Telemetry.error("ChatViewModel.onTalkUpdate", e) }
            }
            return
        }
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
                } catch (e: Exception) {
                    com.iris.android.telemetry.Telemetry.error("ChatViewModel.open", e)
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
        val selected = _reference.value
        val currentPreview = (_preview.value as? Loadable.Ready)?.value
        if (text.isEmpty() || _pending.value || (selected != null &&
            (currentPreview == null || currentPreview.changed || TalkSession.conversation != null))) return
        _pending.value = true
        setDraft("")
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
                    kotlinx.serialization.json.buildJsonObject {
                        put("text", kotlinx.serialization.json.JsonPrimitive(text))
                        if (selected != null) put("evidenceRef",
                            json.encodeToJsonElement(EvidenceRef.serializer(), selected))
                    })
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
                } catch (e: Exception) {
                    com.iris.android.telemetry.Telemetry.error("ChatViewModel.send", e)
                }
                val saved = error is ReplyFailed && error.saved
                if (selected != null) retryEvidence()
                if (!saved && _draft.value.isEmpty()) setDraft(text)
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
