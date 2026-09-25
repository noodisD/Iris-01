package com.iris.android.ui.journal

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.importing.VoiceRecorder
import com.iris.android.ui.theme.LocalIrisColors

@Composable
fun JournalVoiceScreen(onBack: () -> Unit, onReview: (String) -> Unit, model: JournalViewModel = viewModel()) {
    val colors = LocalIrisColors.current
    val progress by model.recordingProgress.collectAsState()
    IrisScaffold(title = "Voice journal", kicker = "journal · record an entry", onBack = onBack) { padding ->
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(padding).padding(horizontal = 20.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Recordings are sent to OpenAI for transcription. Review the transcript and date in Import before adding the entry to your journal.",
                color = colors.ink2)
            IrisCard(Modifier.fillMaxWidth()) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Kicker("record an entry")
                    VoiceRecorder(disabled = progress != null) { file, recordedAt ->
                        val batchId = model.stageRecording(file, recordedAt)
                        onReview(batchId)
                    }
                    if (progress != null) {
                        Kicker("saving recording")
                        LinearProgressIndicator(progress = { progress ?: 0f }, modifier = Modifier.fillMaxWidth(),
                            color = colors.sage, trackColor = colors.lineSoft)
                    }
                }
            }
        }
    }
}
