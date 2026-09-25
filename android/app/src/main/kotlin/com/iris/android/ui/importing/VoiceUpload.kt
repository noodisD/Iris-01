package com.iris.android.ui.importing

import com.iris.android.api.IrisLink
import com.iris.android.api.RecordingUploadResponse
import com.iris.android.api.UploadPart
import java.io.File

/** Stages a recording for transcription; the owner reviews and commits it in Import. */
internal suspend fun stageVoiceRecording(
    file: File,
    recordedAt: String,
    onProgress: (Float) -> Unit,
): RecordingUploadResponse = IrisLink.api().upload("/import/audio", listOf(
    UploadPart("file", file.name, "audio/mp4", null, { file.inputStream() }, file.length()),
    UploadPart("recordedAt", null, null, recordedAt, null, 0),
    UploadPart("capturedSource", null, null, "recording", null, 0),
), RecordingUploadResponse.serializer(), onProgress)
