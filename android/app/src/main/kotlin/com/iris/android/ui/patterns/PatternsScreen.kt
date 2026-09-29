@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.iris.android.ui.patterns

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.SavedStateHandle
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.LocalUriHandler
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.IrisLink
import com.iris.android.api.OCCASION_VERDICTS
import com.iris.android.api.Occasion
import com.iris.android.api.Ok
import com.iris.android.api.PATTERN_VERDICTS
import com.iris.android.api.PatternDetail
import com.iris.android.api.PatternSummary
import com.iris.android.api.PatternsResponse
import com.iris.android.api.DISCOVERY_RANGES
import com.iris.android.api.patternRoute
import com.iris.android.api.patternDiscussionRoute
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.formatEventDate
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/*
 * Discovery, as on the web: general patterns from a library, and the occasions
 * in the owner's writing that are instances of them. A difference between the
 * sides is shown as a difference, never as a cause or advice. Both verdicts are
 * the owner's: whether an occasion belongs, and whether the pattern rings true.
 */

private val RANGE_OPTIONS = listOf(
    "all" to "All available writing", "30d" to "30d", "90d" to "90d",
)
private val TONE_OPTIONS = listOf("better" to "better", "worse" to "worse", "mixed" to "mixed")

class PatternsViewModel(private val savedStateHandle: SavedStateHandle) : ViewModel() {
    val range = savedStateHandle.getStateFlow("range", "all")
    private val _patterns = MutableStateFlow<Loadable<List<PatternSummary>>>(Loadable.Loading)
    val patterns = _patterns.asStateFlow()
    private val _all = MutableStateFlow<List<PatternSummary>>(emptyList())
    val all = _all.asStateFlow()
    private val _unfound = MutableStateFlow(0)
    val unfound = _unfound.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private var generation = 0


    fun refresh() {
        val version = ++generation
        val selected = range.value
        viewModelScope.launch {
            _refreshing.value = true
            if (selected !in DISCOVERY_RANGES) {
                _patterns.value = Loadable.Failed("Unknown reading range: $selected")
                _refreshing.value = false
                return@launch
            }
            try {
                val result = IrisLink.api().send("GET", "/patterns?range=$selected", null, PatternsResponse.serializer())
                if (version == generation) {
                    _all.value = result.patterns
                    val found = result.patterns.filter { it.occasions > 0 && it.verdict?.verdict != "does_not" }
                    _unfound.value = result.patterns.count { it.occasions == 0 && it.rejected == 0 }
                    _patterns.value = Loadable.Ready(found)
                }
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (version == generation) _patterns.value = Loadable.Failed(e.message ?: "Iris couldn't reach your data just now.")
            } finally {
                if (version == generation) _refreshing.value = false
            }
        }
    }
}

@Composable
fun PatternsScreen(onNavigate: (String) -> Unit) {
    val vm: PatternsViewModel = viewModel()
    val state by vm.patterns.collectAsState()
    val all by vm.all.collectAsState()
    val range by vm.range.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val unfound by vm.unfound.collectAsState()
    val colors = LocalIrisColors.current
    RefreshOnReturn(range, vm::refresh)
    IrisScaffold(title = "Patterns", kicker = "from your writing") { padding ->
        RefreshableList(refreshing, vm::refresh) {
            LazyColumn(Modifier.fillMaxWidth().padding(padding),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    RangeChoices(range) { onNavigate("patterns?range=$it") }
                    DiscoveryStatusStrip(onCompletion = vm::refresh)
                }
                when (val s = state) {
                    is Loadable.Loading -> item { LoadingState("Iris is opening the library…") }
                    is Loadable.Failed -> item { ErrorState(s.message, onRetry = vm::refresh) }
                    is Loadable.Ready -> {
                        if (s.value.isEmpty()) item {
                            Column {
                                Text("No source-backed accounts in this reading.", color = colors.ink3)
                                if (range != "all") TextButton(onClick = { onNavigate("patterns?range=all") }) {
                                    Text("All available writing")
                                } else TextButton(onClick = { onNavigate("journal") }) { Text("Open Journal") }
                            }
                        }
                        if (s.value.isNotEmpty()) item { Kicker("worth looking at") }
                        items(s.value.take(3), key = { "featured-${it.id}" }) { p ->
                            PatternPreview(p, range, onNavigate)
                        }
                        if (s.value.size > 3) {
                            item { Kicker("all found situations") }
                            items(s.value.drop(3), key = { "more-${it.id}" }) { p ->
                                PatternPreview(p, range, onNavigate)
                            }
                        }
                        val dismissed = all.filter { it.verdict?.verdict == "does_not" || (it.occasions == 0 && it.rejected > 0) }
                        if (dismissed.isNotEmpty()) {
                            item {
                                var open by rememberSaveable { mutableStateOf(false) }
                                TextButton(onClick = { open = !open }) { Text("Dismissed (${dismissed.size})") }
                                if (open) dismissed.forEach { p ->
                                    TextButton(onClick = { onNavigate(patternRoute(p.id, range)) }) {
                                        Text("${p.name} · ${p.rejected} rejected · review or restore")
                                    }
                                }
                            }
                        }
                    }
                }
                if (unfound > 0) item {
                    Text("$unfound more library lenses not found in this writing",
                        style = IrisType.mono, color = colors.ink4)
                }
            }
        }
    }
}

@Composable
private fun PatternPreview(p: PatternSummary, range: String, onNavigate: (String) -> Unit) {
    val colors = LocalIrisColors.current
    IrisCard(Modifier.fillMaxWidth()) {
        Kicker(if (p.occasions == 1) "one recorded entry · possible lens, not recurrence"
            else "${p.occasions} accounts across ${p.entryCount} entries")
        p.examples.forEach { example ->
            Text(example.response, fontSize = 14.sp, color = colors.ink)
            example.outcome?.let { Text("Then: $it", fontSize = 13.sp, color = colors.ink2) }
            Text("Recorded ${example.recordedOn ?: "date unknown"} · provisionally read as ${example.tone}",
                color = colors.ink3, fontSize = 12.sp)
        }
        Text(p.name, fontFamily = Serif, fontSize = 19.sp, color = colors.ink)
        Text("A library lens, not a measure of how often this happens in life.",
            color = colors.ink3, fontSize = 12.sp)
        TextButton(onClick = { onNavigate(patternRoute(p.id, range)) }) { Text("See examples") }
        TextButton(onClick = { onNavigate(patternDiscussionRoute(p, range)) }) { Text("Explore with Iris") }
    }
}

class PatternDetailViewModel(private val savedStateHandle: SavedStateHandle) : ViewModel() {
    val range = savedStateHandle.getStateFlow("range", "all")
    private val _detail = MutableStateFlow<Loadable<PatternDetail>>(Loadable.Loading)
    val detail = _detail.asStateFlow()
    private val _saving = MutableStateFlow(false)
    val saving = _saving.asStateFlow()
    private val _error = MutableStateFlow<Pair<String, String>?>(null)
    val error = _error.asStateFlow()
    private var loadedId: String? = null
    private var generation = 0


    fun refresh(id: String) {
        val version = ++generation
        val selected = range.value
        if (loadedId != id) { loadedId = id; _detail.value = Loadable.Loading }
        viewModelScope.launch {
            if (selected !in DISCOVERY_RANGES) {
                _detail.value = Loadable.Failed("Unknown reading range: $selected")
                return@launch
            }
            try {
                val result = IrisLink.api().send(
                    "GET", "/patterns/${Uri.encode(id)}?range=$selected", null, PatternDetail.serializer())
                if (version == generation) _detail.value = Loadable.Ready(result)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (version == generation) _detail.value = Loadable.Failed(e.message ?: "Iris couldn't reach your data just now.")
            }
        }
    }

    fun setPatternVerdict(id: String, verdict: String?, note: String?) =
        save(id, "pattern", "/patterns/${Uri.encode(id)}/verdict", verdict, note)

    fun setOccasionFeedback(id: String, occasion: Occasion, verdict: String?, note: String?, ownerTone: String?) =
        save(id, occasion.id, "/patterns/${Uri.encode(id)}/occasions/${Uri.encode(occasion.id)}",
            verdict, note, ownerTone, includeTone = true)

    private fun save(
        id: String, key: String, path: String, verdict: String?, note: String?,
        ownerTone: String? = null, includeTone: Boolean = false,
    ) {
        viewModelScope.launch {
            if (_saving.value) return@launch
            _saving.value = true
            _error.value = null
            // Invalidate any read started before this save, even if it completes while PUT is in flight.
            generation++
            try {
                IrisLink.api().send("PUT", path, buildJsonObject {
                    put("verdict", verdict)
                    put("note", note)
                    if (includeTone) put("ownerTone", ownerTone)
                }.toString(), Ok.serializer())
                refresh(id)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                _error.value = key to (e.message ?: "That didn't save. Try again.")
            } finally {
                _saving.value = false
            }
        }
    }
}

@Composable
fun PatternDetailScreen(id: String, onNavigate: (String) -> Unit, onBack: () -> Unit) {
    val vm: PatternDetailViewModel = viewModel()
    val state by vm.detail.collectAsState()
    val range by vm.range.collectAsState()
    val saving by vm.saving.collectAsState()
    val error by vm.error.collectAsState()
    val colors = LocalIrisColors.current
    val uriHandler = LocalUriHandler.current
    RefreshOnReturn("$id/$range") { vm.refresh(id) }
    val detail = (state as? Loadable.Ready)?.value
    IrisScaffold(title = detail?.pattern?.name ?: "Pattern", kicker = "your recorded situations",
        onBack = onBack) { padding ->
        LazyColumn(Modifier.fillMaxWidth().padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            when (val s = state) {
                is Loadable.Loading -> item { LoadingState("Iris is gathering the occasions…") }
                is Loadable.Failed -> item { ErrorState(s.message, onRetry = { vm.refresh(id) }) }
                is Loadable.Ready -> {
                    val d = s.value
                    item {
                        RangeChoices(range) { onNavigate(patternRoute(id, it)) }
                        Text("${d.coverage.accountCount} recorded accounts across ${d.coverage.entryCount} entries" +
                            if (d.coverage.undatedAccountCount > 0) " · ${d.coverage.undatedAccountCount} undated" else "",
                            color = colors.ink3, fontSize = 12.sp)
                    }
                    if (d.occasions.isEmpty()) item {
                        Column {
                            Text("No source-backed example in this reading. This is only a general library lens.",
                                color = colors.ink3, fontSize = 13.sp)
                            if (range != "all") TextButton(onClick = { onNavigate(patternRoute(id, "all")) }) {
                                Text("All available writing")
                            }
                        }
                    } else {
                        val counted = d.occasions.filter { it.ownerVerdict != "no" }
                        for ((tone, title) in listOf("better" to "read as better", "worse" to "read as worse", "mixed" to "mixed")) {
                            val side = counted.filter { it.tone == tone }
                            if (side.isEmpty() && tone == "mixed") continue
                            item(key = "side-$tone") { Kicker("$title · ${side.size}") }
                            items(side, key = { "o-${it.id}" }) { o ->
                                OccasionCard(o, !saving, onNavigate, error?.takeIf { it.first == o.id }?.second) { verdict, note, ownerTone ->
                                    vm.setOccasionFeedback(id, o, verdict, note, ownerTone)
                                }
                            }
                        }
                        if (counted.none { it.tone == "better" } || counted.none { it.tone == "worse" }) item {
                            Text("No differently classified account in this reading.", color = colors.ink3, fontSize = 12.sp)
                        }
                        if (d.distinctive.isNotEmpty()) item {
                            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Kicker("what else differed between the sides")
                                d.distinctive.forEach { other ->
                                    TextButton(onClick = { onNavigate(patternRoute(other.patternId, range)) }) {
                                        Text("${other.name} · worse ${other.worse}/${other.worseTotal} · " +
                                            "better ${other.better}/${other.betterTotal}", color = colors.ink)
                                    }
                                }
                                Text("At least three accounts on each side, a two-account gap and a 25-point " +
                                    "rate gap. Provisional co-labels, not causes or advice.",
                                    fontSize = 11.sp, color = colors.ink4)
                            }
                        }
                        val rejected = d.occasions.filter { it.ownerVerdict == "no" }
                        if (rejected.isNotEmpty()) {
                            item(key = "side-rejected") { Kicker("you said: not this pattern · ${rejected.size}") }
                            items(rejected, key = { "r-${it.id}" }) { o ->
                                Column(Modifier.alpha(0.6f)) {
                                    OccasionCard(o, !saving, onNavigate, error?.takeIf { it.first == o.id }?.second) { verdict, note, ownerTone ->
                                        vm.setOccasionFeedback(id, o, verdict, note, ownerTone)
                                    }
                                }
                            }
                        }
                        val labelledBy = d.occasions.mapNotNull { it.labelledBy }.distinct()
                        if (labelledBy.isNotEmpty()) item {
                            Text("labelled by: ${labelledBy.joinToString(", ")}", style = IrisType.mono, color = colors.ink4)
                        }
                    }
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Kicker("a question to consider")
                            Text(d.pattern.question, fontSize = 16.sp, color = colors.ink)
                            Kicker("why this lens?")
                            Text(d.pattern.statement, fontSize = 14.sp, color = colors.ink2)
                            if (d.pattern.holdsWhen.isNotEmpty()) Text("It may fit when: ${d.pattern.holdsWhen.joinToString("; ")}",
                                color = colors.ink3, fontSize = 13.sp)
                            if (d.pattern.notWhen.isNotEmpty()) Text("It may not fit when: ${d.pattern.notWhen.joinToString("; ")}",
                                color = colors.ink3, fontSize = 13.sp)
                            d.pattern.basis?.let { Text("General research basis: $it", color = colors.ink3, fontSize = 13.sp) }
                            d.pattern.evidence?.let { Text("Library evidence: $it", color = colors.ink3, fontSize = 13.sp) }
                            d.pattern.source?.let { TextButton(onClick = { uriHandler.openUri(it) }) {
                                Text("Library source")
                            } }
                            Kicker("does it ring true?")
                            FeedbackForm("pattern", PATTERN_VERDICTS, d.verdict?.verdict, d.verdict?.note,
                                !saving, error?.takeIf { it.first == "pattern" }?.second) { verdict, note ->
                                vm.setPatternVerdict(id, verdict, note)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun OccasionCard(
    o: Occasion, enabled: Boolean, onNavigate: (String) -> Unit, error: String?,
    onFeedback: (String?, String?, String?) -> Unit,
) {
    val colors = LocalIrisColors.current
    IrisCard(Modifier.fillMaxWidth()) {
        Kicker(o.recordedOn?.let { "recorded ${formatEventDate(it)}" } ?: "recorded date unknown")
        Text(o.situation, fontSize = 14.sp, color = colors.ink)
        Text(o.response, fontSize = 13.sp, color = colors.ink2)
        o.outcome?.let { Text("→ $it", fontSize = 13.sp, color = colors.ink3) }
        o.explanation?.let { Text("Your interpretation in the entry: “$it”", fontSize = 13.sp,
            fontStyle = FontStyle.Italic, color = colors.ink3) }
        o.citations.forEach { c ->
            Text("“${c.text}”", fontSize = 13.sp, fontStyle = FontStyle.Italic, color = colors.ink3)
            if (c.sourceType == "reflection") {
                TextButton(onClick = { onNavigate("journal?entry=${Uri.encode(c.entryId)}") }) {
                    Text("open entry", color = colors.sage)
                }
            }
        }
        var draftNote by rememberSaveable(o.id) { mutableStateOf(o.verdictNote.orEmpty()) }
        var draftVerdict by rememberSaveable(o.id) { mutableStateOf(o.ownerVerdict) }
        var draftTone by rememberSaveable(o.id) { mutableStateOf(o.ownerTone) }
        var serverNote by rememberSaveable(o.id) { mutableStateOf(o.verdictNote) }
        var serverVerdict by rememberSaveable(o.id) { mutableStateOf(o.ownerVerdict) }
        var serverTone by rememberSaveable(o.id) { mutableStateOf(o.ownerTone) }
        LaunchedEffect(o.verdictNote, o.ownerVerdict, o.ownerTone) {
            if (draftNote == serverNote.orEmpty()) draftNote = o.verdictNote.orEmpty()
            if (draftVerdict == serverVerdict) draftVerdict = o.ownerVerdict
            if (draftTone == serverTone) draftTone = o.ownerTone
            serverNote = o.verdictNote
            serverVerdict = o.ownerVerdict
            serverTone = o.ownerTone
        }
        Kicker("Does this account fit?")
        Choices(OCCASION_VERDICTS, draftVerdict, enabled) {
            draftVerdict = if (draftVerdict == it) null else it
            onFeedback(draftVerdict, draftNote, draftTone)
        }
        Text("Read as ${o.tone} · suggested ${o.suggestedTone}", color = colors.ink3, fontSize = 12.sp)
        Choices(TONE_OPTIONS,
            draftTone, enabled) {
            draftTone = if (draftTone == it) null else it
            onFeedback(draftVerdict, draftNote, draftTone)
        }
        OutlinedTextField(value = draftNote, onValueChange = { draftNote = it }, label = { Text("Your note") },
            enabled = enabled, modifier = Modifier.fillMaxWidth())
        TextButton(onClick = { onFeedback(draftVerdict, draftNote, draftTone) }, enabled = enabled) { Text("Save note") }
        error?.let { Text(it, color = colors.rose, style = IrisType.mono) }
    }
}

@Composable
internal fun RangeChoices(range: String, onSelect: (String) -> Unit) {
    Choices(RANGE_OPTIONS,
        range, true) { if (it != range) onSelect(it) }
}

@Composable
internal fun RefreshOnReturn(key: String, refresh: () -> Unit) {
    val owner = LocalLifecycleOwner.current
    val latestRefresh by rememberUpdatedState(refresh)
    LaunchedEffect(key) { latestRefresh() }
    DisposableEffect(owner, key) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) latestRefresh()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
}

@Composable
internal fun FeedbackForm(
    id: String, options: List<Pair<String, String>>, verdict: String?, note: String?,
    enabled: Boolean, error: String?, onSave: (String?, String?) -> Unit,
) {
    val colors = LocalIrisColors.current
    var draftNote by rememberSaveable(id) { mutableStateOf(note.orEmpty()) }
    var draftVerdict by rememberSaveable(id) { mutableStateOf(verdict) }
    var serverNote by rememberSaveable(id) { mutableStateOf(note) }
    var serverVerdict by rememberSaveable(id) { mutableStateOf(verdict) }
    LaunchedEffect(note, verdict) {
        if (draftNote == serverNote.orEmpty()) draftNote = note.orEmpty()
        if (draftVerdict == serverVerdict) draftVerdict = verdict
        serverNote = note
        serverVerdict = verdict
    }
    Choices(options, draftVerdict, enabled) {
        draftVerdict = if (draftVerdict == it) null else it
        onSave(draftVerdict, draftNote)
    }
    OutlinedTextField(value = draftNote, onValueChange = { draftNote = it }, label = { Text("Your note") },
        enabled = enabled, modifier = Modifier.fillMaxWidth())
    TextButton(onClick = { onSave(draftVerdict, draftNote) }, enabled = enabled) { Text("Save note") }
    error?.let { Text(it, color = colors.rose, style = IrisType.mono) }
}

@Composable
internal fun Choices(options: List<Pair<String, String>>, current: String?, enabled: Boolean, onPick: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (value, label) ->
            if (value == current) {
                FilledTonalButton(onClick = { onPick(value) }, enabled = enabled) { Text(label) }
            } else {
                OutlinedButton(onClick = { onPick(value) }, enabled = enabled) { Text(label) }
            }
        }
    }
}
