package com.iris.android.ui.importing

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.iris.android.api.CommitResult
import com.iris.android.api.ImportAdapter
import com.iris.android.api.ImportBatch
import com.iris.android.api.ImportBulkUpdateResponse
import com.iris.android.api.ImportEntriesResponse
import com.iris.android.api.ImportEntry
import com.iris.android.api.IrisLink
import com.iris.android.api.RecordingUploadResponse
import com.iris.android.api.UploadPart
import com.iris.android.api.json
import com.iris.android.ui.Loadable
import java.io.File
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray

data class ImportProgress(val label: String, val fraction: Float?)

class ImportViewModel : ViewModel() {
    private val _history = MutableStateFlow<Loadable<List<ImportBatch>>>(Loadable.Loading)
    val history = _history.asStateFlow()
    private val _adapters = MutableStateFlow<List<ImportAdapter>>(emptyList())
    val adapters = _adapters.asStateFlow()
    private val _activeId = MutableStateFlow<String?>(null)
    val activeId = _activeId.asStateFlow()
    private val _batch = MutableStateFlow<ImportBatch?>(null)
    val batch = _batch.asStateFlow()
    private val _entries = MutableStateFlow<Loadable<List<ImportEntry>>>(Loadable.Loading)
    val entries = _entries.asStateFlow()
    private val _progress = MutableStateFlow<ImportProgress?>(null)
    val progress = _progress.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error = _error.asStateFlow()
    private val _action = MutableStateFlow<String?>(null)
    val action = _action.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()

    fun clearError() { _error.value = null }

    fun refresh() {
        if (_refreshing.value) return
        _refreshing.value = true
        val historyJob = viewModelScope.launch {
            try {
                _history.value = Loadable.Ready(IrisLink.api().send("GET", "/import/batches", null,
                    ListSerializer(ImportBatch.serializer())))
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) { _history.value = Loadable.Failed(e.message ?: "IRIS could not load your imports.") }
        }
        val adaptersJob = viewModelScope.launch {
            try {
                _adapters.value = IrisLink.api().send("GET", "/import/adapters", null,
                    ListSerializer(ImportAdapter.serializer()))
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) { _error.value = e.message ?: "IRIS could not load import formats." }
        }
        if (_activeId.value != null) refreshBatch()
        viewModelScope.launch {
            try { joinAll(historyJob, adaptersJob) }
            finally { _refreshing.value = false }
        }
    }

    fun open(id: String) {
        _activeId.value = id
        _batch.value = null
        _entries.value = Loadable.Loading
        refreshBatch()
        refreshEntries()
    }

    fun done() {
        _activeId.value = null
        _batch.value = null
        _entries.value = Loadable.Loading
        refreshHistory()
    }

    private fun refreshHistory() = viewModelScope.launch {
        try {
            _history.value = Loadable.Ready(IrisLink.api().send("GET", "/import/batches", null,
                ListSerializer(ImportBatch.serializer())))
        } catch (e: CancellationException) { throw e
        } catch (e: Exception) { _error.value = e.message ?: "IRIS could not load your imports." }
    }

    fun refreshBatch() {
        val id = _activeId.value ?: return
        viewModelScope.launch {
            try {
                val fresh = IrisLink.api().send("GET", "/import/batches/$id", null, ImportBatch.serializer())
                if (_activeId.value == id) _batch.value = fresh
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) { if (_activeId.value == id) _error.value = e.message ?: "IRIS could not load this import." }
        }
    }

    fun refreshEntries() {
        val id = _activeId.value ?: return
        viewModelScope.launch {
            try {
                val all = ArrayList<ImportEntry>()
                var offset = 0
                do {
                    val page = IrisLink.api().send("GET", "/import/batches/$id/entries?limit=500&offset=$offset",
                        null, ImportEntriesResponse.serializer()).entries
                    all.addAll(page)
                    offset += 500
                } while (page.size == 500)
                if (_activeId.value == id) _entries.value = Loadable.Ready(all)
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) {
                if (_activeId.value == id) _entries.value = Loadable.Failed(e.message ?: "IRIS could not load your entries.")
            }
        }
    }

    private fun afterReviewAction() {
        refreshBatch()
        refreshEntries()
    }

    private fun mutate(label: String, block: suspend () -> Unit) {
        if (_action.value != null) return
        _action.value = label
        _error.value = null
        viewModelScope.launch {
            try { block() }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { _error.value = e.message ?: "The request failed." }
            finally { _action.value = null }
        }
    }

    fun setDate(id: String, day: String) = mutate("date") {
        IrisLink.api().send("PATCH", "/import/entries/$id",
            buildJsonObject { put("occurredOn", day) }.toString(), ImportEntry.serializer())
        afterReviewAction()
    }

    fun setStatus(entry: ImportEntry) = mutate("status") {
        val status = if (entry.status == "excluded" || entry.status == "failed") "staged" else "excluded"
        IrisLink.api().send("PATCH", "/import/entries/${entry.id}",
            buildJsonObject { put("status", status) }.toString(), ImportEntry.serializer())
        afterReviewAction()
    }

    fun bulk(ids: List<String>, op: String, day: String? = null) = mutate("bulk") {
        val body = buildJsonObject {
            putJsonArray("ids") { ids.forEach { add(kotlinx.serialization.json.JsonPrimitive(it.toLong())) } }
            put("op", op)
            if (day != null) put("occurredOn", day)
        }
        IrisLink.api().send("POST", "/import/entries/bulk", body.toString(), ImportBulkUpdateResponse.serializer())
        afterReviewAction()
    }

    fun reparse(adapter: String) = mutate("reparse") {
        val id = _activeId.value ?: return@mutate
        IrisLink.api().send("POST", "/import/batches/$id/reparse",
            buildJsonObject { put("adapter", adapter) }.toString(), ImportBatch.serializer())
        afterReviewAction()
    }

    fun commit() = mutate("commit") {
        val id = _activeId.value ?: return@mutate
        IrisLink.api().send("POST", "/import/batches/$id/commit", null, CommitResult.serializer())
        afterReviewAction()
        refreshHistory()
    }

    fun discard(withReflections: Boolean) = mutate("discard") {
        val id = _activeId.value ?: return@mutate
        IrisLink.api().send("DELETE", "/import/batches/$id?withReflections=$withReflections", null, Unit.serializer())
        done()
    }

    fun sendFiles(context: Context, uris: List<Uri>, kind: String) {
        if (uris.isEmpty() || _progress.value != null) return
        _progress.value = ImportProgress("uploading", null)
        _error.value = null
        viewModelScope.launch {
            try {
                var batchId: String? = null
                for ((i, uri) in uris.withIndex()) {
                    val label = if (uris.size > 1) "uploading ${i + 1} of ${uris.size}" else "uploading"
                    val picked = pickedFile(context, uri)
                    _progress.value = ImportProgress(label, if (picked.length < 0) null else 0f)
                    val file = picked.part
                    if (kind == "text") {
                        val parts = listOf(file) + listOfNotNull(picked.lastModified?.let { textPart("lastModified", it.toString()) })
                        val batch = IrisLink.api().upload("/import/batches", parts, ImportBatch.serializer()) {
                            _progress.value = ImportProgress(label, it)
                        }
                        batchId = batch.id
                    } else {
                        val parts = mutableListOf(file, textPart("capturedSource", "upload"))
                        picked.lastModified?.let { parts.add(textPart("recordedAt", Instant.ofEpochMilli(it).toString())) }
                        if (batchId != null) parts.add(textPart("batchId", batchId))
                        batchId = IrisLink.api().upload("/import/audio", parts, RecordingUploadResponse.serializer()) {
                            _progress.value = ImportProgress(label, it)
                        }.batchId
                    }
                }
                if (batchId != null) open(batchId)
                refreshHistory()
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) { _error.value = e.message ?: "The upload failed." }
            finally { _progress.value = null }
        }
    }

    /** Called by the recorder; failures propagate so its review clip is preserved. */
    suspend fun saveRecording(file: File, recordedAt: String) {
        _progress.value = ImportProgress("saving recording", 0f)
        try {
            val staged = stageVoiceRecording(file, recordedAt) {
                _progress.value = ImportProgress("saving recording", it)
            }
            open(staged.batchId)
            refreshHistory()
        } finally { _progress.value = null }
    }
}

private fun textPart(name: String, value: String) = UploadPart(name, null, null, value, null, 0)

private data class PickedFile(val part: UploadPart, val length: Long, val lastModified: Long?)

private fun pickedFile(context: Context, uri: Uri): PickedFile {
    val resolver = context.contentResolver
    var filename = uri.lastPathSegment?.substringAfterLast('/') ?: "upload"
    var size = -1L
    var modified: Long? = null
    resolver.query(uri, null, null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) {
            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (nameIndex >= 0 && !cursor.isNull(nameIndex)) filename = cursor.getString(nameIndex)
            val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
            if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) size = cursor.getLong(sizeIndex)
            val modifiedIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_LAST_MODIFIED)
            if (modifiedIndex >= 0 && !cursor.isNull(modifiedIndex)) modified = cursor.getLong(modifiedIndex)
        }
    }
    val mime = resolver.getType(uri) ?: "application/octet-stream"
    val part = UploadPart("file", filename, mime, null,
        { resolver.openInputStream(uri) ?: throw IOException("The selected file could not be opened.") }, size)
    return PickedFile(part, size, modified)
}
