@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.iris.android.ui.noticed

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.ConstructCandidate
import com.iris.android.api.ConstructCandidatesResponse
import com.iris.android.api.ConstructConfirmResponse
import com.iris.android.api.ConstructRejectResponse
import com.iris.android.api.DiscoveryRun
import com.iris.android.api.DiscoveryRunResponse
import com.iris.android.api.IrisLink
import com.iris.android.api.json
import com.iris.android.ui.DAY_LONG
import com.iris.android.ui.Loadable
import com.iris.android.ui.formatEventDate
import com.iris.android.ui.components.EmptyState
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString

class NoticedViewModel : ViewModel() {
    private val _candidates = MutableStateFlow<Loadable<List<ConstructCandidate>>>(Loadable.Loading)
    val candidates = _candidates.asStateFlow()
    private val _lastRun = MutableStateFlow<DiscoveryRun?>(null)
    val lastRun = _lastRun.asStateFlow()
    private val _discovering = MutableStateFlow(false)
    val discovering = _discovering.asStateFlow()
    private val _discoveryFailed = MutableStateFlow(false)
    val discoveryFailed = _discoveryFailed.asStateFlow()
    private val _decision = MutableStateFlow<Map<String, String>>(emptyMap())
    val decision = _decision.asStateFlow()
    private val _decisionErrors = MutableStateFlow<Set<String>>(emptySet())
    val decisionErrors = _decisionErrors.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            if (_refreshing.value) return@launch
            _refreshing.value = true
            try {
                fetchCandidates()
            } catch (e: Exception) {
                _candidates.value = Loadable.Failed(e.message ?: "Iris couldn't reach your data just now.")
            } finally {
                _refreshing.value = false
            }
            fetchLastRun()
        }
    }

    private suspend fun fetchCandidates() {
        val result = IrisLink.api().send("GET", "/constructs?status=candidate", null, ConstructCandidatesResponse.serializer())
        _candidates.value = Loadable.Ready(result.constructs)
    }

    private suspend fun fetchLastRun() {
        try { _lastRun.value = IrisLink.api().send("GET", "/constructs/last-run", null, DiscoveryRunResponse.serializer()).run }
        catch (_: Exception) { /* The list is still available if last-run metadata fails. */ }
    }

    fun discover(includeStaged: Boolean) {
        viewModelScope.launch {
            if (_discovering.value) return@launch
            _discovering.value = true
            _discoveryFailed.value = false
            try {
                IrisLink.api().send("POST", "/constructs/discover", json.encodeToString(mapOf("includeStaged" to includeStaged)),
                    ConstructCandidatesResponse.serializer())
            } catch (_: Exception) {
                _discoveryFailed.value = true
            } finally {
                _discovering.value = false
                refresh() // A partial read can still write a run, including its drop counts.
            }
        }
    }

    fun decide(id: String, action: String) {
        viewModelScope.launch {
            if (_decision.value.containsKey(id)) return@launch
            _decision.value = _decision.value + (id to action)
            _decisionErrors.value = _decisionErrors.value - id
            try {
                if (action == "confirm") IrisLink.api().send("POST", "/constructs/${Uri.encode(id)}/confirm", "{}", ConstructConfirmResponse.serializer())
                else IrisLink.api().send("POST", "/constructs/${Uri.encode(id)}/reject", "{}", ConstructRejectResponse.serializer())
                fetchCandidates()
            } catch (_: Exception) {
                _decisionErrors.value = _decisionErrors.value + id
            } finally {
                _decision.value = _decision.value - id
            }
        }
    }
}

@Composable
fun NoticedScreen(onNavigate: (String) -> Unit) {
    val vm: NoticedViewModel = viewModel()
    val candidates by vm.candidates.collectAsState()
    val lastRun by vm.lastRun.collectAsState()
    val discovering by vm.discovering.collectAsState()
    val discoveryFailed by vm.discoveryFailed.collectAsState()
    val decisions by vm.decision.collectAsState()
    val decisionErrors by vm.decisionErrors.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    var includeStaged by remember { mutableStateOf(true) }
    val colors = LocalIrisColors.current
    LaunchedEffect(Unit) { vm.refresh() }
    val count = (candidates as? Loadable.Ready)?.value?.size ?: 0
    val title = buildAnnotatedString {
        append("$count to read, ")
        withStyle(SpanStyle(fontStyle = FontStyle.Italic, color = colors.sage)) { append("none counted yet.") }
    }
    IrisScaffold(title = title, kicker = "patterns · awaiting your word") { padding ->
        RefreshableList(refreshing, vm::refresh) {
            LazyColumn(Modifier.fillMaxWidth().padding(padding),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 20.dp, vertical = 20.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp)) {
                when (val state = candidates) {
                    is Loadable.Loading -> item { LoadingState("Iris is fetching what she noticed…") }
                    is Loadable.Failed -> item { ErrorState(onRetry = vm::refresh) }
                    is Loadable.Ready -> {
                        item {
                            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Checkbox(checked = includeStaged, onCheckedChange = { includeStaged = it })
                                    Text("include voice recordings", fontSize = 11.sp, color = colors.ink3)
                                }
                                Button(onClick = { vm.discover(includeStaged) }, enabled = !discovering) {
                                    Text(if (discovering) "Reading your archive…" else "Read my archive")
                                }
                                Kicker("sends your entries to the model", color = colors.ink4)
                            }
                        }
                        if (lastRun != null) item { RunSummary(lastRun!!) }
                        if (discoveryFailed) item {
                            IrisCard(Modifier.fillMaxWidth()) {
                                Text("The read did not finish. Nothing was changed.", color = colors.ink2, fontSize = 12.sp)
                            }
                        }
                        if (state.value.isEmpty()) item {
                            EmptyState("Nothing waiting.",
                                "Reading the archive is something you ask for. When Iris finds something that recurs in your writing, it waits here with the quotes it rests on — and counts for nothing until you say so.")
                        } else items(state.value, key = { it.id }) { candidate ->
                            CandidateCard(candidate, decisions[candidate.id], candidate.id in decisionErrors,
                                onNavigate, { vm.decide(candidate.id, "confirm") }, { vm.decide(candidate.id, "reject") })
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CandidateCard(c: ConstructCandidate, decision: String?, failed: Boolean,
    onNavigate: (String) -> Unit, onConfirm: () -> Unit, onReject: () -> Unit) {
    val colors = LocalIrisColors.current
    IrisCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            if (failed) Text("That didn't save. The pattern is still waiting for your decision.",
                color = colors.rose, fontSize = 12.sp)
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Kicker(if (c.claimKind == "behaviour") "iris noticed · claims something happened"
                    else "iris noticed · counts what you wrote about")
                Text(c.claim, fontFamily = Serif, fontSize = 24.sp, lineHeight = 27.sp, color = colors.ink)
                if (c.spanStart != null && c.spanEnd != null) Kicker(
                    "${formatEventDate(c.spanStart, DAY_LONG)} – ${formatEventDate(c.spanEnd, DAY_LONG)}")
            }
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Kicker("in your own words")
                c.quotes.forEach { quote ->
                    Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                        Spacer(Modifier.width(2.dp).fillMaxHeight().background(colors.sageDim))
                        Column(Modifier.weight(1f)) {
                            Text("\"${quote.text}\"", fontFamily = Serif, fontStyle = FontStyle.Italic,
                                lineHeight = 25.sp, fontSize = 17.sp, color = colors.ink)
                            if (quote.citable && quote.entryId != null) {
                                TextButton(onClick = { onNavigate("journal?entry=${Uri.encode(quote.entryId)}") },
                                    contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) {
                                    Text("read the entry ↗", style = IrisType.mono, color = colors.sage)
                                }
                            } else Kicker("from a recording · undated, so it is never counted", color = colors.ink4)
                        }
                    }
                }
            }
            Button(onClick = onConfirm, enabled = decision == null, modifier = Modifier.fillMaxWidth()) {
                Text(if (decision == "confirm") "Measuring…" else "Yes — count this in my writing")
            }
            OutlinedButton(onClick = onReject, enabled = decision == null, modifier = Modifier.fillMaxWidth()) {
                Text(if (decision == "reject") "Setting aside…" else "Not me")
            }
            Text("Counts how often this comes up in what you wrote. Not how often you did it.",
                fontSize = 11.sp, color = colors.ink4)
        }
    }
}

@Composable
private fun RunSummary(run: DiscoveryRun) {
    val d = run.dropped
    val unchecked = d.unchecked + d.incomplete
    val letGo = listOfNotNull(
        d.mergedAway.takeIf { it != 0 }?.let { "$it merged into another" },
        unchecked.takeIf { it != 0 }?.let { "$it because support could not be checked" },
        d.denied.takeIf { it != 0 }?.let { "$it because a quote denied the claim" },
        d.tooFewSupporting.takeIf { it != 0 }?.let { "$it with too few supporting quotes" },
        d.alreadyDecided.takeIf { it != 0 }?.let { "$it you had already decided on" },
        d.notEmbedded.takeIf { it != 0 }?.let { "$it that could not be stored" },
    )
    fun plural(n: Int, singular: String) = "$n ${if (n == 1) singular else "${singular}s"}"
    val summary = buildString {
        append("${plural(run.rawFindings, "finding")}, ${plural(run.staged, "proposal")}.")
        if (run.status != "complete") append(" ${run.passesCompleted} of ${run.passesPlanned} passes finished.")
        if (run.dropsRecorded) {
            if (letGo.isNotEmpty()) append(" Let go: ${letGo.joinToString(", ")}.")
        } else append(" This read was made before IRIS counted what it let go.")
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Kicker("last read")
        Text(summary, fontSize = 13.sp, lineHeight = 21.sp, color = LocalIrisColors.current.ink2)
    }
}
