package com.iris.android.ui.patterns

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.DISCOVERY_RANGES
import com.iris.android.api.DayDifference
import com.iris.android.api.DayDifferencesResponse
import com.iris.android.api.DayDiagnostics
import com.iris.android.api.InsightsResponse
import com.iris.android.api.IrisLink
import com.iris.android.api.Ok
import com.iris.android.api.PersonalInsight
import com.iris.android.api.SavedFeedback
import com.iris.android.api.PATTERN_VERDICTS
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.EmptyState
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.theme.LocalIrisColors
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class InsightsViewModel(private val savedStateHandle: SavedStateHandle) : ViewModel() {
    val range = savedStateHandle.getStateFlow("range", "all")
    private val _insights = MutableStateFlow<Loadable<InsightsResponse>>(Loadable.Loading)
    val insights = _insights.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private val _saving = MutableStateFlow(false)
    val saving = _saving.asStateFlow()
    private val _error = MutableStateFlow<Pair<String, String>?>(null)
    val error = _error.asStateFlow()
    private val _dayDifferences = MutableStateFlow<Loadable<DayDifferencesResponse>>(Loadable.Loading)
    val dayDifferences = _dayDifferences.asStateFlow()
    private val _refreshingDays = MutableStateFlow(false)
    val refreshingDays = _refreshingDays.asStateFlow()
    private val _savingDay = MutableStateFlow(false)
    val savingDay = _savingDay.asStateFlow()
    private val _dayError = MutableStateFlow<Pair<String, String>?>(null)
    val dayError = _dayError.asStateFlow()
    private var writingGeneration = 0
    private var daysGeneration = 0

    fun refresh() { refreshInsights(); refreshDays() }

    private fun refreshInsights() {
        val version = ++writingGeneration
        val selected = range.value
        viewModelScope.launch {
            _refreshing.value = true
            try {
                require(selected in DISCOVERY_RANGES)
                val result = IrisLink.api().send("GET", "/personal-insights?range=$selected", null, InsightsResponse.serializer())
                if (version == writingGeneration) _insights.value = Loadable.Ready(result)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (version == writingGeneration) _insights.value = Loadable.Failed(e.message ?: "Writing insights unavailable.")
            } finally { if (version == writingGeneration) _refreshing.value = false }
        }
    }

    fun refreshDays() {
        val version = ++daysGeneration
        val selected = range.value
        viewModelScope.launch {
            _refreshingDays.value = true
            try {
                require(selected in DISCOVERY_RANGES)
                val result = IrisLink.api().send("GET", "/day-differences?range=$selected", null, DayDifferencesResponse.serializer())
                if (version == daysGeneration) _dayDifferences.value = Loadable.Ready(result)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (version == daysGeneration) _dayDifferences.value = Loadable.Failed(e.message ?: "Measured days unavailable.")
            } finally { if (version == daysGeneration) _refreshingDays.value = false }
        }
    }

    fun judge(insight: PersonalInsight, verdict: String?, note: String?) {
        viewModelScope.launch {
            if (_saving.value) return@launch
            _saving.value = true
            _error.value = null
            writingGeneration++
            try {
                IrisLink.api().send("PUT", "/personal-insights/${Uri.encode(insight.id)}/verdict",
                    buildJsonObject {
                        put("range", range.value); put("snapshot", insight.snapshot)
                        put("verdict", verdict); put("note", note)
                    }.toString(), SavedFeedback.serializer())
                refreshInsights()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                _error.value = insight.id to (e.message ?: "That didn't save. Review current evidence and retry.")
                refreshInsights()
            } finally { _saving.value = false }
        }
    }

    fun judgeDay(d: DayDifference, verdict: String?, note: String?) {
        viewModelScope.launch {
            if (_savingDay.value) return@launch
            _savingDay.value = true
            _dayError.value = null
            daysGeneration++
            try {
                IrisLink.api().send("PUT", "/day-differences/${Uri.encode(d.outcome)}/${Uri.encode(d.split)}/verdict",
                    buildJsonObject { put("verdict", verdict); put("note", note) }.toString(), Ok.serializer())
                refreshDays()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                _dayError.value = "${d.outcome}/${d.split}" to (e.message ?: "That didn't save. Try again.")
            } finally { _savingDay.value = false }
        }
    }
}

@Composable
fun InsightsScreen(onNavigate: (String) -> Unit, selectedId: String? = null, onBack: (() -> Unit)? = null) {
    val vm: InsightsViewModel = viewModel()
    val range by vm.range.collectAsState()
    val state by vm.insights.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val saving by vm.saving.collectAsState()
    val error by vm.error.collectAsState()
    val dayState by vm.dayDifferences.collectAsState()
    val refreshingDays by vm.refreshingDays.collectAsState()
    val savingDay by vm.savingDay.collectAsState()
    val dayError by vm.dayError.collectAsState()
    val colors = LocalIrisColors.current
    var filter by rememberSaveable(range) { mutableStateOf("current") }
    RefreshOnReturn("$range/$selectedId", vm::refresh)
    IrisScaffold(title = if (selectedId == null) "Insights" else "Insight",
        kicker = "from your writing", onBack = onBack) { padding ->
        RefreshableList(refreshing || refreshingDays, vm::refresh) {
            LazyColumn(Modifier.fillMaxWidth().padding(padding),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    RangeChoices(range) { onNavigate(if (selectedId == null) "insights?range=$it" else "insights/${Uri.encode(selectedId)}?range=$it") }
                    DiscoveryStatusStrip(onCompletion = vm::refresh)
                    Kicker("From your writing")
                }
                when (val s = state) {
                    is Loadable.Loading -> item { LoadingState("Opening personal insights…") }
                    is Loadable.Failed -> item { ErrorState(s.message, onRetry = vm::refresh) }
                    is Loadable.Ready -> {
                        val data = s.value
                        if (data.status.stage != "ready") item {
                            Text("Personal insights are ${data.status.stage}; previous claims are unavailable.", color = colors.ink3)
                        } else if (selectedId != null) {
                            val selected = data.insights.find { it.id == selectedId }
                            if (selected == null) item {
                                Text("This saved insight is unavailable in the current view.", color = colors.ink3)
                                TextButton(onClick = { onNavigate("insights?range=$range") }) { Text("Current insights") }
                            } else item {
                                PersonalInsightCard(selected, range, onNavigate, !saving,
                                    error?.takeIf { it.first == selected.id }?.second, vm::judge, initiallyExpanded = true)
                            }
                        } else {
                            item {
                                Text("${data.coverage.entryCount} writing entries considered · recorded " +
                                    "${data.coverage.recordedFrom ?: "date unknown"} to ${data.coverage.recordedTo ?: "date unknown"}.",
                                    color = colors.ink3, fontSize = 12.sp)
                                Choices(listOf("current" to "Current", "saved" to "Saved opinions",
                                    "dismissed" to "Dismissed"), filter, true) { filter = it }
                            }
                            val cards = data.insights.filter {
                                when (filter) {
                                    "dismissed" -> it.feedback?.verdict == "does_not"
                                    "saved" -> it.feedback?.verdict != null || it.feedback?.note != null
                                    else -> it.feedback?.verdict != "does_not"
                                }
                            }
                            if (cards.isEmpty()) item {
                                EmptyState("No current writing insight in this view.",
                                    "A checked relation needs enough independent evidence. Missing outcomes are not treated as negative results.")
                            }
                            items(cards, key = { it.id }) { insight ->
                                PersonalInsightCard(insight, range, onNavigate, !saving,
                                    error?.takeIf { it.first == insight.id }?.second, vm::judge)
                            }
                        }
                    }
                }
                if (selectedId == null) {
                    item {
                        Kicker("Measured day differences")
                        Text("Explicit check-ins against confirmed phone measurements. Observations, not causes.",
                            color = colors.ink3, fontSize = 13.sp)
                    }
                    when (val s = dayState) {
                        is Loadable.Loading -> item { LoadingState("Comparing measured days…") }
                        is Loadable.Failed -> item { ErrorState(s.message, onRetry = vm::refreshDays) }
                        is Loadable.Ready -> {
                            val data = s.value
                            if (data.differences.isEmpty()) item {
                                EmptyState("No qualifying day comparison.", dayReason(data.diagnostics))
                            }
                            items(data.differences, key = { "day/$range/${it.outcome}/${it.split}" }) { d ->
                                MeasuredCard(d, range, onNavigate, !savingDay,
                                    dayError?.takeIf { it.first == "${d.outcome}/${d.split}" }?.second, vm::judgeDay)
                            }
                            item {
                                Text("${data.diagnostics.measuredDays} measured · ${data.diagnostics.checkinDays} check-in · " +
                                    "${data.diagnostics.overlappingDays} overlapping days", color = colors.ink3, fontSize = 12.sp)
                                TextButton(onClick = { onNavigate("journal") }) { Text("Journal") }
                                TextButton(onClick = { onNavigate("sensors") }) { Text("Sensors") }
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun dayReason(d: DayDiagnostics) = when (d.reason) {
    "no_measured_days" -> "No confirmed measured days in this period. Review Sensors."
    "no_checkins" -> "No explicit check-in scores in this period. Review Journal."
    "no_overlap" -> "Measured days and check-ins do not overlap."
    "insufficient_groups" -> "No comparison has five valid days in each group."
    "no_qualifying_difference" -> "The existing difference and permutation gates were not met."
    else -> "Review Journal and Sensors for contributing days."
}
