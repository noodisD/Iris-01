@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.iris.android.ui.patterns

import android.net.Uri
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.DayDifference
import com.iris.android.api.DayDifferencesResponse
import com.iris.android.api.Difference
import com.iris.android.api.DifferencesResponse
import com.iris.android.api.DifferenceDetail
import com.iris.android.api.DayDifferenceDetail
import com.iris.android.api.DayDiagnostics
import com.iris.android.api.OutcomePair
import com.iris.android.api.Occasion
import com.iris.android.api.IrisLink
import com.iris.android.api.Ok
import com.iris.android.api.DISCOVERY_RANGES
import com.iris.android.api.patternRoute
import com.iris.android.api.pairDiscussionRoute
import com.iris.android.api.coLabelDiscussionRoute
import com.iris.android.api.dayDiscussionRoute
import com.iris.android.api.PATTERN_VERDICTS
import com.iris.android.ui.Loadable
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/*
 * Insights compares outcomes on pattern occasions and on measured phone/Timeline
 * days. These are differences between groups, not causes; the owner's verdict
 * is independent for each comparison.
 */

class InsightsViewModel(private val savedStateHandle: SavedStateHandle) : ViewModel() {
    val range = savedStateHandle.getStateFlow("range", "all")
    private val _differences = MutableStateFlow<Loadable<DifferencesResponse>>(Loadable.Loading)
    val differences = _differences.asStateFlow()
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


    fun refresh() {
        refreshPatterns()
        refreshDays()
    }

    private fun refreshPatterns() {
        val version = ++writingGeneration
        val selected = range.value
        viewModelScope.launch {
            _refreshing.value = true
            if (selected !in DISCOVERY_RANGES) {
                _differences.value = Loadable.Failed("Unknown reading range: $selected")
                _refreshing.value = false
                return@launch
            }
            try {
                val result = IrisLink.api().send("GET", "/differences?range=$selected", null, DifferencesResponse.serializer())
                if (version == writingGeneration) _differences.value = Loadable.Ready(result)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (version == writingGeneration) _differences.value =
                    Loadable.Failed(e.message ?: "Iris couldn't reach your data just now.")
            } finally {
                if (version == writingGeneration) _refreshing.value = false
            }
        }
    }

    fun refreshDays() {
        val version = ++daysGeneration
        val selected = range.value
        viewModelScope.launch {
            _refreshingDays.value = true
            if (selected !in DISCOVERY_RANGES) {
                _dayDifferences.value = Loadable.Failed("Unknown reading range: $selected")
                _refreshingDays.value = false
                return@launch
            }
            try {
                val result = IrisLink.api().send("GET", "/day-differences?range=$selected", null, DayDifferencesResponse.serializer())
                if (version == daysGeneration) _dayDifferences.value = Loadable.Ready(result)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (version == daysGeneration) _dayDifferences.value =
                    Loadable.Failed(e.message ?: "Iris couldn't reach your day comparisons just now.")
            } finally {
                if (version == daysGeneration) _refreshingDays.value = false
            }
        }
    }

    fun judge(d: Difference, verdict: String?, note: String?) {
        viewModelScope.launch {
            if (_saving.value) return@launch
            _saving.value = true
            _error.value = null
            _refreshing.value = false
            writingGeneration++
            try {
                IrisLink.api().send("PUT",
                    "/differences/${Uri.encode(d.patternId)}/${Uri.encode(d.otherId)}/verdict",
                    buildJsonObject { put("verdict", verdict); put("note", note) }.toString(), Ok.serializer())
                refreshPatterns()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                _error.value = "${d.patternId}/${d.otherId}" to (e.message ?: "That didn't save. Try again.")
            } finally {
                _saving.value = false
            }
        }
    }
    fun judgePair(pair: com.iris.android.api.OutcomePair, verdict: String?, note: String?) {
        viewModelScope.launch {
            if (_saving.value) return@launch
            _saving.value = true
            _error.value = null
            writingGeneration++
            try {
                IrisLink.api().send("PUT", "/patterns/${Uri.encode(pair.patternId)}/verdict",
                    buildJsonObject { put("verdict", verdict); put("note", note) }.toString(),
                    Ok.serializer())
                refreshPatterns()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                _error.value = "pair/${pair.patternId}" to (e.message ?: "That didn't save. Try again.")
            } finally { _saving.value = false }
        }
    }


    fun judgeDay(d: DayDifference, verdict: String?, note: String?) {
        viewModelScope.launch {
            if (_savingDay.value) return@launch
            _savingDay.value = true
            _dayError.value = null
            _refreshingDays.value = false
            daysGeneration++
            try {
                IrisLink.api().send("PUT",
                    "/day-differences/${Uri.encode(d.outcome)}/${Uri.encode(d.split)}/verdict",
                    buildJsonObject { put("verdict", verdict); put("note", note) }.toString(), Ok.serializer())
                refreshDays()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                _dayError.value = "${d.outcome}/${d.split}" to (e.message ?: "That didn't save. Try again.")
            } finally {
                _savingDay.value = false
            }
        }
    }
}

@Composable
fun InsightsScreen(onNavigate: (String) -> Unit) {
    val vm: InsightsViewModel = viewModel()
    val range by vm.range.collectAsState()
    val state by vm.differences.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val saving by vm.saving.collectAsState()
    val error by vm.error.collectAsState()
    val dayState by vm.dayDifferences.collectAsState()
    val refreshingDays by vm.refreshingDays.collectAsState()
    val savingDay by vm.savingDay.collectAsState()
    val dayError by vm.dayError.collectAsState()
    val colors = LocalIrisColors.current
    var filter by rememberSaveable(range) { mutableStateOf("current") }
    var showAll by rememberSaveable(range) { mutableStateOf(false) }
    RefreshOnReturn(range, vm::refresh)
    IrisScaffold(title = "Insights", kicker = "situations to consider") { padding ->
        RefreshableList(refreshing || refreshingDays, vm::refresh) {
            LazyColumn(Modifier.fillMaxWidth().padding(padding),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    RangeChoices(range) { onNavigate("insights?range=$it") }
                    DiscoveryStatusStrip(onCompletion = vm::refresh)
                    Text("Recorded situations and measured days to compare, not causes or advice.",
                        color = colors.ink3, fontSize = 13.sp)
                    Kicker("from your writing")
                }
                when (val s = state) {
                    is Loadable.Loading -> item { LoadingState("Comparing recorded situations…") }
                    is Loadable.Failed -> item { ErrorState(s.message, onRetry = vm::refresh) }
                    is Loadable.Ready -> {
                        val data = s.value
                        item {
                            Text("${data.coverage.entryCount} contributing entries · " +
                                "recorded ${data.coverage.recordedFrom ?: "date unknown"} to " +
                                "${data.coverage.recordedTo ?: "date unknown"}. Unwritten events are not absences.",
                                color = colors.ink3, fontSize = 12.sp)
                            Choices(listOf("current" to "Current", "saved" to "Saved opinions",
                                "dismissed" to "Dismissed"), filter, true) {
                                filter = it
                                showAll = false
                            }
                        }
                        val cards = buildList<WritingCard> {
                            data.differences.forEach { add(WritingCard.Contrast(it)) }
                            data.reflections.forEach { add(WritingCard.Pairing(it)) }
                        }.filter { card ->
                            when (filter) {
                                "dismissed" -> card.dismissed
                                "saved" -> !card.dismissed && card.verdict != null
                                else -> !card.dismissed
                            }
                        }
                        val used = mutableSetOf<String>()
                        val featured = cards.filter { card -> used.size < 3 && used.add(card.patternId) }
                        val rest = cards.filterNot { it in featured }
                        if (cards.isEmpty()) item {
                            EmptyState("No writing comparisons in this view.",
                                "No current recorded accounts meet the conservative comparison rule. " +
                                    "Review Journal or read existing writing.")
                        }
                        items(featured + if (showAll) rest else emptyList(), key = { it.key }) { card ->
                            when (card) {
                                is WritingCard.Contrast -> ContrastCard(card.d, range, onNavigate,
                                    !saving, error?.takeIf { it.first == "${card.d.patternId}/${card.d.otherId}" }?.second,
                                    vm::judge)
                                is WritingCard.Pairing -> PairCard(card.pair, range, onNavigate,
                                    !saving, error?.takeIf { it.first == "pair/${card.pair.patternId}" }?.second,
                                    vm::judgePair)
                            }
                        }
                        if (rest.isNotEmpty()) item {
                            TextButton(onClick = { showAll = !showAll }) {
                                Text(if (showAll) "Show fewer" else "Show all comparisons (${rest.size} more)")
                            }
                        }
                    }
                }
                item {
                    Kicker("days compared")
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
                                dayError?.takeIf { it.first == "${d.outcome}/${d.split}" }?.second,
                                vm::judgeDay)
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

internal sealed interface WritingCard {
    val patternId: String
    val verdict: String?
    val dismissed: Boolean
    val key: String
    data class Contrast(val d: Difference) : WritingCard {
        override val patternId get() = d.patternId
        override val verdict get() = d.verdict?.verdict
        override val dismissed get() = d.dismissed
        override val key get() = "co/${d.patternId}/${d.otherId}"
    }
    data class Pairing(val pair: OutcomePair) : WritingCard {
        override val patternId get() = pair.patternId
        override val verdict get() = pair.verdict?.verdict
        override val dismissed get() = verdict == "does_not"
        override val key get() = "pair/${pair.patternId}"
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
