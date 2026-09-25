@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.iris.android.ui.patterns

import android.net.Uri
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
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.Difference
import com.iris.android.api.DifferencesResponse
import com.iris.android.api.IrisLink
import com.iris.android.api.Ok
import com.iris.android.api.PATTERN_VERDICTS
import com.iris.android.api.awaitingFirst
import com.iris.android.api.differenceSentence
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
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/*
 * Insights: differences in outcome, as on the web. Patterns shows what keeps
 * coming up; this shows what goes with it going better or worse. A difference
 * between two sets of occasions, not a cause; whether it rings true is the
 * owner's to say.
 */

class InsightsViewModel : ViewModel() {
    private val _differences = MutableStateFlow<Loadable<List<Difference>>>(Loadable.Loading)
    val differences = _differences.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private val _saving = MutableStateFlow(false)
    val saving = _saving.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error = _error.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            if (_refreshing.value) return@launch
            _refreshing.value = true
            try {
                val result = IrisLink.api().send("GET", "/differences", null, DifferencesResponse.serializer())
                _differences.value = Loadable.Ready(awaitingFirst(result.differences))
            } catch (e: Exception) {
                _differences.value = Loadable.Failed(e.message ?: "Iris couldn't reach your data just now.")
            } finally {
                _refreshing.value = false
            }
        }
    }

    fun judge(d: Difference, verdict: String) {
        viewModelScope.launch {
            if (_saving.value) return@launch
            _saving.value = true
            _error.value = null
            try {
                IrisLink.api().send("PUT",
                    "/differences/${Uri.encode(d.patternId)}/${Uri.encode(d.otherId)}/verdict",
                    buildJsonObject { put("verdict", verdict) }.toString(), Ok.serializer())
                refresh()
            } catch (e: Exception) {
                _error.value = e.message ?: "That didn't save."
            } finally {
                _saving.value = false
            }
        }
    }
}

@Composable
fun InsightsScreen(onNavigate: (String) -> Unit) {
    val vm: InsightsViewModel = viewModel()
    val state by vm.differences.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val saving by vm.saving.collectAsState()
    val error by vm.error.collectAsState()
    val colors = LocalIrisColors.current
    LaunchedEffect(Unit) { vm.refresh() }
    IrisScaffold(title = "Insights", kicker = "insights · differences in outcome") { padding ->
        RefreshableList(refreshing, vm::refresh) {
            LazyColumn(Modifier.fillMaxWidth().padding(padding),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    Text("For each pattern in your writing, the other patterns that were there more often when it " +
                        "went one way than the other. A difference, not a cause: say whether it rings true.",
                        color = colors.ink3, fontSize = 13.sp)
                }
                error?.let { item { Text(it, color = colors.rose, style = IrisType.mono) } }
                when (val s = state) {
                    is Loadable.Loading -> item { LoadingState("Iris is comparing the occasions…") }
                    is Loadable.Failed -> item { ErrorState(onRetry = vm::refresh) }
                    is Loadable.Ready -> if (s.value.isEmpty()) item {
                        EmptyState("No differences yet.",
                            "An insight needs a pattern with occasions that went both better and worse, and " +
                                "another pattern that sits on one side by two or more.")
                    } else items(s.value, key = { "${it.patternId}/${it.otherId}" }) { d ->
                        val current = d.verdict?.verdict
                        IrisCard(Modifier.fillMaxWidth().alpha(if (current == "does_not") 0.55f else 1f)) {
                            if (current != null) Kicker("judged")
                            Text(differenceSentence(d), fontFamily = Serif, fontSize = 18.sp,
                                lineHeight = 25.sp, color = colors.ink)
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                TextButton(onClick = { onNavigate("patterns/${Uri.encode(d.patternId)}") }) {
                                    Text("${d.patternName} →", color = colors.sage)
                                }
                                TextButton(onClick = { onNavigate("patterns/${Uri.encode(d.otherId)}") }) {
                                    Text("${d.otherName} →", color = colors.ink3)
                                }
                            }
                            Choices(PATTERN_VERDICTS, current, !saving) { vm.judge(d, it) }
                        }
                    }
                }
            }
        }
    }
}
