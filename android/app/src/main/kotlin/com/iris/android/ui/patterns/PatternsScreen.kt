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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
import com.iris.android.api.byOccasions
import com.iris.android.api.toneCounts
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

class PatternsViewModel : ViewModel() {
    private val _patterns = MutableStateFlow<Loadable<List<PatternSummary>>>(Loadable.Loading)
    val patterns = _patterns.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            if (_refreshing.value) return@launch
            _refreshing.value = true
            try {
                val result = IrisLink.api().send("GET", "/patterns", null, PatternsResponse.serializer())
                _patterns.value = Loadable.Ready(byOccasions(result.patterns))
            } catch (e: Exception) {
                _patterns.value = Loadable.Failed(e.message ?: "Iris couldn't reach your data just now.")
            } finally {
                _refreshing.value = false
            }
        }
    }
}

@Composable
fun PatternsScreen(onNavigate: (String) -> Unit) {
    val vm: PatternsViewModel = viewModel()
    val state by vm.patterns.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val colors = LocalIrisColors.current
    LaunchedEffect(Unit) { vm.refresh() }
    IrisScaffold(title = "Patterns", kicker = "patterns · a general library") { padding ->
        RefreshableList(refreshing, vm::refresh) {
            LazyColumn(Modifier.fillMaxWidth().padding(padding),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    Text("Patterns known in general, and how many times each turns up in your own writing.",
                        color = colors.ink3, fontSize = 13.sp)
                }
                when (val s = state) {
                    is Loadable.Loading -> item { LoadingState("Iris is opening the library…") }
                    is Loadable.Failed -> item { ErrorState(onRetry = vm::refresh) }
                    is Loadable.Ready -> items(s.value, key = { it.id }) { p ->
                        val verdict = PATTERN_VERDICTS.firstOrNull { it.first == p.verdict?.verdict }?.second
                        IrisCard(Modifier.fillMaxWidth().alpha(if (p.verdict?.verdict == "does_not") 0.55f else 1f),
                            onClick = { onNavigate("patterns/${Uri.encode(p.id)}") }) {
                            Text(p.name, fontFamily = Serif, fontSize = 19.sp, color = colors.ink)
                            Text(toneCounts(p) + (verdict?.let { " · $it" } ?: ""), style = IrisType.mono,
                                color = if (p.occasions > 0) colors.ink3 else colors.ink4)
                        }
                    }
                }
            }
        }
    }
}

class PatternDetailViewModel : ViewModel() {
    private val _detail = MutableStateFlow<Loadable<PatternDetail>>(Loadable.Loading)
    val detail = _detail.asStateFlow()
    private val _saving = MutableStateFlow(false)
    val saving = _saving.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error = _error.asStateFlow()
    private var loadedId: String? = null

    fun refresh(id: String) {
        viewModelScope.launch {
            if (loadedId != id) { loadedId = id; _detail.value = Loadable.Loading }
            try {
                _detail.value = Loadable.Ready(IrisLink.api().send(
                    "GET", "/patterns/${Uri.encode(id)}", null, PatternDetail.serializer()))
            } catch (e: Exception) {
                _detail.value = Loadable.Failed(e.message ?: "Iris couldn't reach your data just now.")
            }
        }
    }

    fun setPatternVerdict(id: String, verdict: String) =
        save(id, "/patterns/${Uri.encode(id)}/verdict", verdict)

    /** Pressing the current answer again clears it. */
    fun setOccasionVerdict(id: String, occasion: Occasion, verdict: String) =
        save(id, "/patterns/${Uri.encode(id)}/occasions/${Uri.encode(occasion.id)}",
            if (occasion.ownerVerdict == verdict) null else verdict)

    private fun save(id: String, path: String, verdict: String?) {
        viewModelScope.launch {
            if (_saving.value) return@launch
            _saving.value = true
            _error.value = null
            try {
                IrisLink.api().send("PUT", path, buildJsonObject { put("verdict", verdict) }.toString(), Ok.serializer())
                refresh(id)
            } catch (e: Exception) {
                _error.value = e.message ?: "That didn't save."
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
    val saving by vm.saving.collectAsState()
    val error by vm.error.collectAsState()
    val colors = LocalIrisColors.current
    LaunchedEffect(id) { vm.refresh(id) }
    val detail = (state as? Loadable.Ready)?.value
    IrisScaffold(title = detail?.pattern?.name ?: "Pattern",
        kicker = detail?.pattern?.evidence?.let { "the idea: $it" } ?: "a pattern from the library",
        onBack = onBack) { padding ->
        LazyColumn(Modifier.fillMaxWidth().padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            when (val s = state) {
                is Loadable.Loading -> item { LoadingState("Iris is gathering the occasions…") }
                is Loadable.Failed -> item { ErrorState(onRetry = { vm.refresh(id) }) }
                is Loadable.Ready -> {
                    val d = s.value
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(d.pattern.statement, fontSize = 16.sp, lineHeight = 23.sp, color = colors.ink2)
                            d.pattern.basis?.let { Text(it, fontSize = 13.sp, color = colors.ink3) }
                        }
                    }
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Kicker("does it ring true?")
                            Choices(PATTERN_VERDICTS, d.verdict?.verdict, !saving) { vm.setPatternVerdict(id, it) }
                            error?.let { Text(it, color = colors.rose, style = IrisType.mono) }
                        }
                    }
                    if (d.occasions.isEmpty()) item {
                        Text("None found in the current reading of your archive. That can mean it is rare for you, " +
                            "or that the labelling missed it: labelling misses some occasions and includes some " +
                            "that do not belong.", color = colors.ink3, fontSize = 13.sp)
                    } else {
                        val counted = d.occasions.filter { it.ownerVerdict != "no" }
                        for ((tone, title) in listOf("worse" to "went worse", "better" to "went better", "mixed" to "mixed")) {
                            val side = counted.filter { it.tone == tone }
                            if (side.isEmpty() && tone == "mixed") continue
                            item(key = "side-$tone") { Kicker("$title · ${side.size}") }
                            items(side, key = { "o-${it.id}" }) { o ->
                                OccasionCard(o, !saving, onNavigate) { vm.setOccasionVerdict(id, o, it) }
                            }
                        }
                        if (d.distinctive.isNotEmpty()) item {
                            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Kicker("what else differed between the sides")
                                d.distinctive.forEach { other ->
                                    TextButton(onClick = { onNavigate("patterns/${Uri.encode(other.patternId)}") }) {
                                        Text("${other.name} · ${other.worse} worse · ${other.better} better", color = colors.ink)
                                    }
                                }
                                Text("Differences of two or more occasions. A difference between two sets of " +
                                    "occasions, not a cause and not advice.", fontSize = 11.sp, color = colors.ink4)
                            }
                        }
                        val rejected = d.occasions.filter { it.ownerVerdict == "no" }
                        if (rejected.isNotEmpty()) {
                            item(key = "side-rejected") { Kicker("you said: not this pattern · ${rejected.size}") }
                            items(rejected, key = { "r-${it.id}" }) { o ->
                                Column(Modifier.alpha(0.6f)) {
                                    OccasionCard(o, !saving, onNavigate) { vm.setOccasionVerdict(id, o, it) }
                                }
                            }
                        }
                        val labelledBy = d.occasions.mapNotNull { it.labelledBy }.distinct()
                        if (labelledBy.isNotEmpty()) item {
                            Text("labelled by: ${labelledBy.joinToString(", ")}", style = IrisType.mono, color = colors.ink4)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun OccasionCard(o: Occasion, enabled: Boolean, onNavigate: (String) -> Unit, onVerdict: (String) -> Unit) {
    val colors = LocalIrisColors.current
    IrisCard(Modifier.fillMaxWidth()) {
        Kicker(o.occurredOn?.let { formatEventDate(it) } ?: "undated")
        Text(o.situation, fontSize = 14.sp, color = colors.ink)
        Text(o.response, fontSize = 13.sp, color = colors.ink2)
        o.outcome?.let { Text("→ $it", fontSize = 13.sp, color = colors.ink3) }
        o.citations.take(2).forEach { c ->
            Text("“${c.text}”", fontSize = 13.sp, fontStyle = FontStyle.Italic, color = colors.ink3)
            if (c.sourceType == "reflection") {
                TextButton(onClick = { onNavigate("journal?entry=${Uri.encode(c.entryId)}") }) {
                    Text("open entry", color = colors.sage)
                }
            }
        }
        Choices(OCCASION_VERDICTS, o.ownerVerdict, enabled, onVerdict)
        o.verdictNote?.let { Text(it, fontSize = 11.sp, color = colors.ink4) }
    }
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
