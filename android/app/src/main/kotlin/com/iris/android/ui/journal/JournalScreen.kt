@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.iris.android.ui.journal

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.painterResource
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.R
import com.iris.android.api.JournalEntry
import com.iris.android.api.RecurringPhrase
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RecordingPlayer
import com.iris.android.ui.components.RecordingSource
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.formatEventDate
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Mono
import com.iris.android.ui.theme.Serif
import java.util.Locale
import kotlinx.coroutines.flow.collect

private val prompts = listOf("What happened today?", "What were you feeling?", "What do you want Iris to remember?")

@Composable
fun JournalScreen(entry: String? = null, onNavigate: (String) -> Unit, model: JournalViewModel = viewModel()) {
    val colors = LocalIrisColors.current
    val pages by model.pages.collectAsState()
    val lines by model.lines.collectAsState()
    val energy by model.energy.collectAsState()
    val saving by model.saving.collectAsState()
    val saveError by model.saveError.collectAsState()
    val refreshing by model.refreshing.collectAsState()
    val loadingOlder by model.loadingOlder.collectAsState()
    val pagingError by model.pagingError.collectAsState()
    val snackbar = remember { SnackbarHostState() }
    val scrollState = rememberLazyListState()
    LaunchedEffect(model) { model.refresh() }
    LaunchedEffect(model, snackbar) { model.messages.collect { snackbar.showSnackbar(it) } }
    val loaded = (pages as? Loadable.Ready)?.value
    val foundIndex = loaded?.entries?.indexOfFirst { it.id == entry } ?: -1
    LaunchedEffect(entry, loaded?.entries?.size, loaded?.nextCursor, loadingOlder, refreshing, pagingError) {
        if (entry != null && foundIndex < 0 && loaded?.nextCursor != null && !loadingOlder && !refreshing && !pagingError) {
            model.loadOlder()
        }
    }
    LaunchedEffect(entry, foundIndex) {
        if (entry != null && foundIndex >= 0) scrollState.animateScrollToItem(foundIndex + 2)
    }
    val title = buildAnnotatedString {
        append("Three lines, ")
        withStyle(SpanStyle(fontStyle = FontStyle.Italic, color = colors.sage)) { append("please.") }
    }
    IrisScaffold(title = title, kicker = "today · evening", snackbarHostState = snackbar) { padding ->
        RefreshableList(refreshing = refreshing, onRefresh = model::refresh) {
            LazyColumn(
                state = scrollState,
                modifier = Modifier.fillMaxWidth(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                    start = 20.dp, end = 20.dp, top = padding.calculateTopPadding(), bottom = padding.calculateBottomPadding() + 24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                when (val result = pages) {
                    Loadable.Loading -> item(key = "loading") { LoadingState("Iris is opening your journal…") }
                    is Loadable.Failed -> item(key = "failed") { ErrorState(onRetry = model::refresh) }
                    is Loadable.Ready -> {
                        val data = result.value
                        item(key = "composer") {
                            JournalComposer(lines, energy, saving, saveError, model::setLine, model::selectEnergy, model::save)
                        }
                        item(key = "voice") {
                            IrisCard(Modifier.fillMaxWidth()) {
                                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Kicker("voice journal · today")
                                    Text("Speak freely. Iris will transcribe your recording; review it in Import before it appears in your journal.",
                                        color = colors.ink2, fontSize = 13.sp)
                                    Button(onClick = { onNavigate("journal/voice") }, modifier = Modifier.fillMaxWidth()) {
                                        Icon(painterResource(R.drawable.ic_mic), contentDescription = null)
                                        Text("Record an entry", modifier = Modifier.padding(start = 8.dp))
                                    }
                                }
                            }
                        }
                        item(key = "entries-heading") {
                            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Kicker("your entries · newest first")
                                Text("${data.entries.size} shown${if (data.nextCursor == null) ", all of them" else ""}",
                                    fontFamily = Serif, fontSize = 24.sp, color = colors.ink)
                            }
                        }
                        itemsIndexed(data.entries, key = { _, item -> item.id }) { _, item ->
                            JournalEntryRow(item, highlighted = item.id == entry)
                        }
                        item(key = "older") {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                                if (data.nextCursor != null) {
                                    OutlinedButton(onClick = if (pagingError) model::retryOlder else model::loadOlder,
                                        enabled = !loadingOlder) {
                                        Text(if (loadingOlder) "Loading…" else "older entries ↓")
                                    }
                                } else Text("back to the beginning", fontFamily = Mono, fontSize = 10.sp,
                                    letterSpacing = 0.8.sp, color = colors.ink4)
                            }
                        }
                        if (data.recurringPhrases.isNotEmpty()) item(key = "phrases") {
                            RecurringPhrases(data.recurringPhrases)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun JournalComposer(
    lines: List<String>, energy: Int?, saving: Boolean, saveError: String?,
    onLine: (Int, String) -> Unit, onEnergy: (Int?) -> Unit, onSave: () -> Unit,
) {
    val colors = LocalIrisColors.current
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Kicker("energy · optional")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (n in 1..10) {
                val selected = energy == n
                Text("$n", modifier = Modifier.size(32.dp)
                    .background(if (selected) colors.sage else colors.bg0, CircleShape)
                    .border(1.dp, if (selected) colors.sage else colors.line, CircleShape)
                    .clickable { onEnergy(if (selected) null else n) }
                    .semantics { contentDescription = "energy $n" }
                    .padding(top = 7.dp),
                    fontFamily = Mono, fontSize = 11.sp, color = if (selected) colors.bg1 else colors.ink3,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            }
            TextButton(onClick = { onEnergy(null) }, enabled = energy != null,
                modifier = Modifier.semantics { contentDescription = "record no energy for this entry" }) {
                Text("clear", fontFamily = Mono, fontSize = 10.sp, color = colors.ink4)
            }
        }
        prompts.forEachIndexed { i, prompt ->
            Column(Modifier.fillMaxWidth().drawBehind {
                drawLine(colors.line, Offset(0f, size.height), Offset(size.width, size.height), 1.dp.toPx())
            }.padding(vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("0${i + 1}", fontFamily = Mono, fontSize = 10.sp, color = colors.ink4)
                    Text(prompt, fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = 18.sp, color = colors.ink3)
                }
                BasicTextField(
                    value = lines[i], onValueChange = { onLine(i, it) }, minLines = 2,
                    modifier = Modifier.fillMaxWidth().padding(start = 28.dp),
                    textStyle = androidx.compose.ui.text.TextStyle(fontFamily = Serif, fontSize = 19.sp, color = colors.ink),
                    cursorBrush = SolidColor(colors.sage),
                )
            }
        }
        Button(onClick = onSave, enabled = !saving && lines.any { it.isNotEmpty() }, modifier = Modifier.fillMaxWidth()) {
            Text(if (saving) "Saving…" else "Save entry")
        }
        if (saveError != null) Text("Not saved: $saveError", fontFamily = Mono, fontSize = 12.sp, color = colors.rose)
    }
}

@Composable
private fun JournalEntryRow(entry: JournalEntry, highlighted: Boolean) {
    val colors = LocalIrisColors.current
    val shape = RoundedCornerShape(8.dp)
    Column(
        modifier = Modifier.fillMaxWidth()
            .then(if (highlighted) Modifier.background(colors.sage.copy(alpha = 0.06f), shape)
                .border(1.dp, colors.sageDim, shape).padding(10.dp) else Modifier),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text((entry.occurredOn?.let(::formatEventDate) ?: "undated").uppercase(Locale.getDefault()), fontFamily = Mono,
                fontSize = 10.sp, letterSpacing = 0.8.sp, color = colors.ink3)
            if (!entry.tags.isNullOrEmpty()) Text(entry.tags.joinToString(" ") { "·$it" },
                fontFamily = Mono, fontSize = 9.sp, color = colors.ink4)
        }
        Text(entry.lines.joinToString(" "), color = colors.ink2, fontSize = 13.sp, lineHeight = 20.sp)
        entry.audioUrl?.let { RecordingPlayer(RecordingSource.Remote(it, entry.id)) }
        entry.irisNote?.let { note ->
            Row(Modifier.padding(top = 4.dp)
                .drawBehind { drawLine(colors.sageDim, Offset.Zero, Offset(0f, size.height), 1.dp.toPx()) }
                .padding(start = 10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("iris:", fontFamily = Mono, fontSize = 10.sp, color = colors.sage)
                Text(note, fontSize = 12.sp, fontStyle = FontStyle.Italic, color = colors.ink2)
            }
        }
    }
}

@Composable
private fun RecurringPhrases(phrases: List<RecurringPhrase>) {
    val colors = LocalIrisColors.current
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Spacer(Modifier.fillMaxWidth().height(20.dp).drawBehind {
            drawLine(colors.line, Offset(0f, size.height / 2), Offset(size.width, size.height / 2),
                1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 4.dp.toPx())))
        })
        Kicker("phrases iris keeps hearing")
        phrases.forEach { phrase ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text("\"${phrase.phrase}\"", modifier = Modifier.weight(1f),
                    fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = 14.sp,
                    color = colors.ink, maxLines = 3, overflow = TextOverflow.Ellipsis)
                Text("×${phrase.count}", fontFamily = Mono, fontSize = 10.sp, color = colors.ink3)
            }
        }
    }
}
