package com.iris.android.ui.journal

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.iris.android.api.IrisLink
import com.iris.android.api.Checkin
import com.iris.android.api.JournalEntry
import com.iris.android.api.JournalListResponse
import com.iris.android.api.RecurringPhrase
import com.iris.android.api.json
import com.iris.android.ui.Loadable
import com.iris.android.ui.importing.stageVoiceRecording
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString

@Serializable
private data class NewEntry(
    val text: String,
    val format: String = "markdown",
    val checkin: Checkin? = null,
)

data class JournalPages(
    val entries: List<JournalEntry>,
    val nextCursor: String?,
    val recurringPhrases: List<RecurringPhrase>,
)

class JournalViewModel : ViewModel() {
    private val _pages = MutableStateFlow<Loadable<JournalPages>>(Loadable.Loading)
    val pages = _pages.asStateFlow()

    private val _text = MutableStateFlow("")
    val text = _text.asStateFlow()
    private val _selection = MutableStateFlow(0 to 0)
    val selection = _selection.asStateFlow()
    private val _checkin = MutableStateFlow(Checkin())
    val checkin = _checkin.asStateFlow()
    private val _saving = MutableStateFlow(false)
    val saving = _saving.asStateFlow()
    private val _saveError = MutableStateFlow<String?>(null)
    val saveError = _saveError.asStateFlow()
    private val _recordingProgress = MutableStateFlow<Float?>(null)
    val recordingProgress = _recordingProgress.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private val _loadingOlder = MutableStateFlow(false)
    val loadingOlder = _loadingOlder.asStateFlow()
    private val _pagingError = MutableStateFlow(false)
    val pagingError = _pagingError.asStateFlow()
    private val _messages = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val messages = _messages.asSharedFlow()
    private var listJob: Job? = null

    fun setDraft(value: String, start: Int, end: Int) {
        _text.value = value
        _selection.value = start to end
    }

    fun applyEdit(edit: MarkdownEdit) {
        _text.value = edit.text
        _selection.value = edit.start to edit.end
    }

    fun selectCheckin(field: String, value: Int?) {
        val current = _checkin.value
        _checkin.value = when (field) {
            "energy" -> current.copy(energy = value)
            "mood" -> current.copy(mood = value)
            "sleep" -> current.copy(sleepQuality = value)
            "stress" -> current.copy(stress = value)
            "focus" -> current.copy(focus = value)
            else -> current
        }
    }

    fun refresh() {
        listJob?.cancel()
        val hasPrevious = _pages.value is Loadable.Ready
        if (!hasPrevious) _pages.value = Loadable.Loading
        _refreshing.value = hasPrevious
        _loadingOlder.value = false
        _pagingError.value = false
        listJob = viewModelScope.launch {
            try {
                val result = IrisLink.api().send("GET", "/journal", null, JournalListResponse.serializer())
                _pages.value = Loadable.Ready(JournalPages(result.entries, result.nextCursor, result.recurringPhrases.orEmpty()))
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (hasPrevious) _messages.emit(error.message ?: "Iris couldn't reach your data just now.")
                else _pages.value = Loadable.Failed(error.message ?: "Iris couldn't reach your data just now.")
            } finally {
                _refreshing.value = false
            }
        }
    }

    fun loadOlder() {
        val current = (_pages.value as? Loadable.Ready)?.value ?: return
        val cursor = current.nextCursor ?: return
        if (_loadingOlder.value || _refreshing.value || _pagingError.value) return
        _loadingOlder.value = true
        listJob = viewModelScope.launch {
            try {
                val result = IrisLink.api().send("GET", "/journal?cursor=${Uri.encode(cursor)}", null, JournalListResponse.serializer())
                val latest = (_pages.value as? Loadable.Ready)?.value ?: return@launch
                if (latest.nextCursor == cursor) {
                    _pages.value = Loadable.Ready(latest.copy(
                        entries = latest.entries + result.entries,
                        nextCursor = result.nextCursor,
                    ))
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                _pagingError.value = true
                _messages.emit(error.message ?: "Iris couldn't reach your data just now.")
            } finally {
                _loadingOlder.value = false
            }
        }
    }

    fun retryOlder() {
        _pagingError.value = false
        loadOlder()
    }

    fun save() {
        if (_saving.value) return
        val draft = _checkin.value
        val hasCheckin = listOf(draft.energy, draft.mood, draft.sleepQuality, draft.stress, draft.focus).any { it != null }
        if (_text.value.isBlank() && !hasCheckin) return
        _saving.value = true
        _saveError.value = null
        viewModelScope.launch {
            try {
                val body = NewEntry(_text.value, checkin = if (hasCheckin) draft else null)
                IrisLink.api().send("POST", "/journal", json.encodeToString(body), JournalEntry.serializer())
                _text.value = ""
                _selection.value = 0 to 0
                _checkin.value = Checkin()
                refresh()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                _saveError.value = error.message ?: error.toString()
            } finally {
                _saving.value = false
            }
        }
    }

    /** A recording remains staged until the owner reviews and commits it in Import. */
    suspend fun stageRecording(file: File, recordedAt: String): String {
        check(_recordingProgress.value == null) { "A recording is already being saved." }
        _recordingProgress.value = 0f
        try {
            return stageVoiceRecording(file, recordedAt) { _recordingProgress.value = it }.batchId
        } finally {
            _recordingProgress.value = null
        }
    }

}
