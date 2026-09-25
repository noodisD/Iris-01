@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class, androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.iris.android.ui.importing

import androidx.compose.foundation.border
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.ImportAdapter
import com.iris.android.api.ImportBatch
import com.iris.android.api.ImportEntry
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ConfirmDialog
import com.iris.android.ui.components.EmptyState
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Mono
import com.iris.android.ui.theme.Serif
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import kotlinx.coroutines.delay

@Composable
fun ImportScreen(batchToReview: String? = null, vm: ImportViewModel = viewModel()) {
    val context = LocalContext.current
    val colors = LocalIrisColors.current
    val history by vm.history.collectAsState()
    val adapters by vm.adapters.collectAsState()
    val activeId by vm.activeId.collectAsState()
    val batch by vm.batch.collectAsState()
    val entries by vm.entries.collectAsState()
    val error by vm.error.collectAsState()
    val progress by vm.progress.collectAsState()
    val action by vm.action.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    var confirmUndo by remember { mutableStateOf(false) }
    var bulkDate by remember(activeId) { mutableStateOf<String?>(null) }
    val writtenPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) {
        vm.sendFiles(context, it, "text")
    }
    val audioPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) {
        vm.sendFiles(context, it, "audio")
    }

    LaunchedEffect(Unit) { vm.refresh() }
    LaunchedEffect(batchToReview) { if (batchToReview != null) vm.open(batchToReview) }
    LaunchedEffect(activeId, batch?.status, batch?.counts?.awaitingTranscript) {
        if (activeId != null && (batch?.status == "parsing" || batch?.status == "committing" ||
                (batch?.counts?.awaitingTranscript ?: 0) > 0)) {
            while (true) { delay(1_500); vm.refreshBatch() }
        }
    }
    LaunchedEffect(activeId, batch?.kind, batch?.status) {
        if (activeId != null && batch?.kind == "audio" && batch?.status in listOf("needs_review", "failed")) {
            while (true) { delay(2_000); vm.refreshEntries() }
        }
    }
    if (confirmUndo && batch != null) ConfirmDialog(
        "Remove all ${batch!!.committedCount} entries this import created?", "undo this import",
        onConfirm = { confirmUndo = false; vm.discard(true) }, onDismiss = { confirmUndo = false },
    )

    val title = buildAnnotatedString {
        append("Everything before this")
        withStyle(SpanStyle(color = colors.sage, fontStyle = FontStyle.Italic)) { append(".") }
    }
    IrisScaffold(title = title, kicker = "import · what you have already written") { padding ->
        RefreshableList(refreshing = refreshing, onRefresh = vm::refresh) {
            LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(horizontal = 20.dp, vertical = 20.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp)) {
                if (history is Loadable.Loading) item { LoadingState("Iris is checking what you have brought…") }
                else if (history is Loadable.Failed) item { ErrorState((history as Loadable.Failed).message, vm::refresh) }
                else {
                    if (error != null) item { ErrorState(error, vm::clearError) }
                    if (progress != null) item {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Kicker(progress!!.label)
                            if (progress!!.fraction == null) LinearProgressIndicator(Modifier.fillMaxWidth().height(3.dp), color = colors.sage)
                            else LinearProgressIndicator(progress = { progress!!.fraction!! }, modifier = Modifier.fillMaxWidth().height(3.dp), color = colors.sage,
                                trackColor = colors.lineSoft)
                        }
                    }
                    when {
                        activeId != null && batch == null -> item { LoadingState("Iris is reading your export…") }
                        batch?.status == "parsing" || batch?.status == "committing" -> item {
                            LoadingState(if (batch?.status == "parsing") "Iris is reading your export…" else "Iris is adding your entries…")
                        }
                        batch?.status == "needs_review" || (batch?.status == "failed" && batch!!.counts.total > 0) -> {
                            item { ReviewHeader(batch!!, adapters, entries, bulkDate, { bulkDate = it }, vm, action) }
                            when (val e = entries) {
                                Loadable.Loading -> item { LoadingState("Iris is reading your entries…") }
                                is Loadable.Failed -> item { ErrorState(e.message, vm::refreshEntries) }
                                is Loadable.Ready -> items(e.value, key = { it.id }) { entry ->
                                    EntryRow(entry, action == null, vm)
                                }
                            }
                            item { ReviewFooter(batch!!, action, vm) }
                        }
                        batch?.status == "committed" -> item { Finished(batch!!, action, vm, { vm.done() }, { confirmUndo = true }) }
                        batch?.status == "failed" -> item { ErrorState(batch!!.error ?: "That export could not be read.", vm::done) }
                        activeId == null -> {
                            item {
                                DropZone("written journals",
                                    "An export from Notion, Obsidian, Day One — a zip, a folder of notes, or one long file. Iris will show you what it found before anything is saved.",
                                    progress != null) { writtenPicker.launch(arrayOf("*/*")) }
                            }
                            item {
                                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                    DropZone("voice journals",
                                        "Recordings from your phone. They are sent to OpenAI to be transcribed; the audio itself is kept here so you can listen back.",
                                        progress != null) { audioPicker.launch(arrayOf("audio/*", "video/mp4")) }
                                    VoiceRecorder(disabled = progress != null, onSave = vm::saveRecording)
                                }
                            }
                            val batches = (history as Loadable.Ready<List<ImportBatch>>).value
                            if (batches.isEmpty()) item {
                                EmptyState("Nothing imported yet", "Whatever you have written elsewhere can come in here, dated when you wrote it.")
                            } else {
                                item { Kicker("previous imports") }
                                items(batches, key = { it.id }) { b ->
                                    Row(Modifier.fillMaxWidth().clickable { vm.open(b.id) }.padding(vertical = 12.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(b.originalFilename ?: "recording", color = colors.ink2, fontSize = 13.sp,
                                            modifier = Modifier.weight(1f), maxLines = 2)
                                        Spacer(Modifier.width(12.dp))
                                        Text("${if (b.status == "committed") "${b.committedCount} imported" else b.status} · ${localDay(b.createdAt)}",
                                            style = IrisType.mono, color = colors.ink4, fontSize = 10.sp)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun localDay(instant: String): String = runCatching {
    val date = OffsetDateTime.parse(instant).atZoneSameInstant(ZoneId.systemDefault()).toLocalDate()
    date.format(DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT))
}.getOrElse { instant }

@Composable
private fun DropZone(label: String, hint: String, disabled: Boolean, onClick: () -> Unit) {
    val colors = LocalIrisColors.current
    Box(Modifier.fillMaxWidth().alpha(if (disabled) 0.6f else 1f).clickable(enabled = !disabled, onClick = onClick)) {
        Canvas(Modifier.matchParentSize()) {
            drawRoundRect(colors.bg2, cornerRadius = CornerRadius(10.dp.toPx()))
            drawRoundRect(colors.line, cornerRadius = CornerRadius(10.dp.toPx()),
                style = Stroke(1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(7.dp.toPx(), 5.dp.toPx()))))
        }
        Column(Modifier.padding(horizontal = 22.dp, vertical = 28.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Kicker(label)
            Text(hint, fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = 16.sp, color = colors.ink2)
        }
    }
}

@Composable
private fun ReviewHeader(batch: ImportBatch, adapters: List<ImportAdapter>, entries: Loadable<List<ImportEntry>>,
    bulkDate: String?, onBulkDate: (String) -> Unit, vm: ImportViewModel, action: String?) {
    val colors = LocalIrisColors.current
    val counts = batch.counts
    val all = (entries as? Loadable.Ready)?.value.orEmpty()
    val undated = all.filter { it.occurredOn == null && !it.dateUnknownAccepted && it.status == "staged" }.map { it.id }
    val fileDatable = all.filter { it.occurredOn == null && it.status == "staged" && it.fileModifiedOn != null }.map { it.id }
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (batch.status == "failed") {
            Column(Modifier.fillMaxWidth().bordered(colors.line).padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("${counts.imported} of ${counts.total} entries were imported; ${counts.failed} failed.", color = colors.ink, fontSize = 13.sp)
                Text("The ones that landed are safe and are not here. Put the rest right below and import again, or discard what is left.",
                    color = colors.ink3, fontSize = 12.sp)
                if (batch.error != null) Text(batch.error, color = colors.ink4, style = IrisType.mono)
            }
        }
        Kicker("read as")
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            var expanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { if (action == null) expanded = it }) {
                OutlinedTextField(value = adapters.firstOrNull { it.name == batch.adapter }?.label ?: batch.adapter.orEmpty(),
                    onValueChange = {}, readOnly = true, modifier = Modifier.menuAnchor().width(180.dp),
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) }, singleLine = true,
                    enabled = action != "reparse")
                ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                    adapters.forEach { adapter -> DropdownMenuItem(text = { Text(adapter.label) }, onClick = {
                        expanded = false
                        vm.reparse(adapter.name)
                    }) }
                }
            }
            Text(if (action == "reparse") "re-reading…" else "change if this looks wrong",
                color = colors.ink4, fontSize = 11.sp, fontStyle = FontStyle.Italic)
        }
        TextButton(onClick = { vm.discard(false) }, enabled = action == null) { Text("discard this import", color = colors.ink4) }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("${counts.total} entries", style = IrisType.mono, color = colors.ink2)
            if (counts.needsDate > 0) Text("${counts.needsDate} need a date", style = IrisType.mono, color = colors.rose)
            if (counts.duplicate > 0) Text("${counts.duplicate} already imported", style = IrisType.mono, color = colors.amber)
            if (counts.excluded > 0) Text("${counts.excluded} excluded", style = IrisType.mono, color = colors.ink4)
            if (counts.earliest != null) Text("${counts.earliest} → ${counts.latest}", style = IrisType.mono, color = colors.ink3)
        }
        if (fileDatable.isNotEmpty()) {
            Column(Modifier.fillMaxWidth().bordered(colors.amber).padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("${fileDatable.size} undated ${if (fileDatable.size == 1) "entry" else "entries"} can be dated by when ${if (fileDatable.size == 1) "its file was" else "their files were"} last saved. That is a guess (a note is often edited after the day it describes), so those dates stay amber for you to check.",
                    color = colors.ink2, fontSize = 12.5.sp)
                OutlinedButton(onClick = { vm.bulk(fileDatable, "use_file_date") }, enabled = action == null) { Text("use file dates") }
            }
        }
        if (undated.isNotEmpty()) {
            Column(Modifier.fillMaxWidth().bordered(colors.rose).padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("${undated.size} ${if (undated.size == 1) "entry has" else "entries have"} no date IRIS could read. It will not guess one — an entry filed on the wrong day is counted in the wrong week for good.",
                    color = colors.ink2, fontSize = 12.5.sp)
                DateChip(bulkDate, false, onBulkDate)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { vm.bulk(undated, "set_date", bulkDate) }, enabled = bulkDate != null && action == null) { Text("set all") }
                    OutlinedButton(onClick = { vm.bulk(undated, "accept_unknown_date") }, enabled = action == null) { Text("accept as undated") }
                    TextButton(onClick = { vm.bulk(undated, "exclude") }, enabled = action == null) { Text("exclude all") }
                }
            }
        }
    }
}

private fun Modifier.bordered(color: Color): Modifier = border(1.dp, color, RoundedCornerShape(8.dp))

@Composable
private fun DateChip(value: String?, probable: Boolean, onDate: (String) -> Unit) {
    val colors = LocalIrisColors.current
    var picker by remember { mutableStateOf(false) }
    val border = if (value == null && !probable) colors.rose else if (probable) colors.amber else colors.lineSoft
    AssistChip(onClick = { picker = true }, label = {
        Text(value ?: "yyyy-mm-dd", fontFamily = Mono, fontSize = 11.sp, color = if (value == null) colors.ink4 else colors.ink)
    }, border = BorderStroke(1.dp, border))
    if (picker) {
        val initial = remember(value) { value?.let { runCatching { LocalDate.parse(it).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli() }.getOrNull() } }
        val state = rememberDatePickerState(initialSelectedDateMillis = initial)
        DatePickerDialog(onDismissRequest = { picker = false }, confirmButton = {
            TextButton(onClick = {
                state.selectedDateMillis?.let { millis -> onDate(Instant.ofEpochMilli(millis).atZone(ZoneOffset.UTC).toLocalDate().toString()) }
                picker = false
            }, enabled = state.selectedDateMillis != null) { Text("OK") }
        }, dismissButton = { TextButton(onClick = { picker = false }) { Text("Cancel") } }) { DatePicker(state) }
    }
}

@Composable
private fun EntryRow(entry: ImportEntry, enabled: Boolean, vm: ImportViewModel) {
    val colors = LocalIrisColors.current
    val excluded = entry.status == "excluded"
    val retryable = entry.status == "failed"
    val badge = when (entry.status) {
        "excluded" -> colors.ink4; "duplicate" -> colors.amber; "imported" -> colors.sage
        "failed" -> colors.rose; else -> colors.ink3
    }
    Column(Modifier.fillMaxWidth().alpha(if (excluded) 0.4f else 1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DateChip(entry.occurredOn, entry.dateConfidence == "probable") { vm.setDate(entry.id, it) }
            Text(entry.status.uppercase(), fontFamily = Mono, fontSize = 9.5.sp, color = badge, modifier = Modifier.weight(1f))
            IconButton(onClick = { vm.setStatus(entry) }, enabled = enabled,
                modifier = Modifier.semantics { contentDescription = if (retryable) "try this entry again" else if (excluded) "include this entry" else "exclude this entry" }) {
                Text(if (excluded || retryable) "+" else "×", color = if (excluded || retryable) colors.sage else colors.ink4, fontSize = 20.sp)
            }
        }
        Text(entry.excerpt.ifBlank { if (entry.hasAudio) "Waiting for the transcript…" else "(empty)" },
            color = colors.ink2, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Text("${entry.sourceName.orEmpty()}${if (entry.hasAudio) " · recording" else ""}", fontFamily = Mono, fontSize = 9.5.sp, color = colors.ink4)
        if (entry.dateSource == "mtime") Text("dated by when its file was last saved · a guess", fontFamily = Mono,
            fontSize = 9.5.sp, color = colors.amber)
        if (entry.occurredOn == null && entry.fileModifiedOn != null && !excluded) {
            TextButton(onClick = { vm.bulk(listOf(entry.id), "use_file_date") }, enabled = enabled, contentPadding = PaddingValues(0.dp)) {
                Text("file last saved ${entry.fileModifiedOn}. Use that?", color = colors.amber, fontSize = 10.5.sp)
            }
        }
        entry.warnings.forEach { Text(it, color = colors.amber, fontSize = 10.5.sp, fontStyle = FontStyle.Italic) }
        if (entry.error != null) Text(entry.error, color = colors.rose, fontSize = 10.5.sp)
    }
}

@Composable
private fun ReviewFooter(batch: ImportBatch, action: String?, vm: ImportViewModel) {
    val colors = LocalIrisColors.current
    val counts = batch.counts
    val waiting = counts.awaitingTranscript > 0
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Button(onClick = vm::commit, enabled = counts.needsDate == 0 && !waiting && counts.staged > 0 && action == null) {
            Text(if (action == "commit") "importing…" else "Import ${counts.staged} entries")
        }
        if (counts.needsDate > 0) Text("Set or exclude the undated entries first.", color = colors.rose,
            fontSize = 11.5.sp, fontStyle = FontStyle.Italic)
        else if (waiting) Text("${counts.awaitingTranscript} recording(s) still being transcribed…", color = colors.ink3,
            fontSize = 11.5.sp, fontStyle = FontStyle.Italic)
    }
}

@Composable
private fun Finished(batch: ImportBatch, action: String?, vm: ImportViewModel, onDone: () -> Unit, onUndo: () -> Unit) {
    val colors = LocalIrisColors.current
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("${batch.committedCount} entries added to your journal.", fontFamily = Serif, fontSize = 22.sp, color = colors.ink)
        Text("Iris is still reading them. Embedding and pattern-finding happen in the background, so themes may take a few minutes to appear — and a large import can reorganise the ones you already have.",
            fontSize = 13.sp, color = colors.ink3)
        OutlinedButton(onClick = onDone) { Text("Import something else") }
        TextButton(onClick = onUndo, enabled = action != "discard") { Text("undo this import", color = colors.rose) }
    }
}
