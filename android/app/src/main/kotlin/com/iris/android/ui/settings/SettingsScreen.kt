@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.iris.android.ui.settings

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.R
import com.iris.android.Settings
import com.iris.android.api.AnalysisPreferences
import com.iris.android.api.IrisLink
import com.iris.android.api.KnownFact
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ConfirmDialog
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisOrb
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

private val engineLabels = mapOf(
    "trajectory" to "whether something is growing or fading",
    "tension" to "themes pulling in different directions",
    "resolution" to "whether a pattern has settled",
    "leverage" to "what tends to come before what",
    "decision_impact" to "what changed after a decision",
    "lifelong" to "how often something recurred across the whole record",
    "observations" to "what reading your entries noticed",
)

internal class SettingsViewModel : ViewModel() {
    private val _facts = MutableStateFlow<Loadable<List<KnownFact>>>(Loadable.Loading)
    val facts = _facts.asStateFlow()
    private val _analysis = MutableStateFlow<AnalysisPreferences?>(null)
    val analysis = _analysis.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private val _busy = MutableStateFlow(false)
    val busy = _busy.asStateFlow()
    private val _confirmFact = MutableStateFlow<KnownFact?>(null)
    val confirmFact = _confirmFact.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error = _error.asStateFlow()

    fun refresh() {
        if (_refreshing.value) return
        viewModelScope.launch {
            _refreshing.value = true
            try {
                _facts.value = Loadable.Ready(IrisLink.api().send("GET", "/knowledge", null,
                    ListSerializer(KnownFact.serializer())))
            } catch (e: Exception) {
                _facts.value = Loadable.Failed(e.message ?: e.toString())
            } finally {
                _refreshing.value = false
            }
            refreshAnalysis()
        }
    }

    private suspend fun refreshAnalysis() {
        try {
            _analysis.value = IrisLink.api().send("GET", "/user/analysis", null, AnalysisPreferences.serializer())
        } catch (e: Exception) {
            _error.value = e.message ?: e.toString()
        }
    }

    fun requestForget(fact: KnownFact) {
        if (fact.source == "confirmed") _confirmFact.value = fact else forget(fact)
    }
    fun cancelForget() { _confirmFact.value = null }
    fun confirmForget() { _confirmFact.value?.let(::forget) }

    private fun forget(fact: KnownFact) {
        if (_busy.value) return
        viewModelScope.launch {
            _confirmFact.value = null
            _busy.value = true
            try {
                IrisLink.api().send("DELETE", "/knowledge/${fact.id}", null, Unit.serializer())
                _facts.value = Loadable.Ready(IrisLink.api().send("GET", "/knowledge", null,
                    ListSerializer(KnownFact.serializer())))
            } catch (e: Exception) { _error.value = e.message ?: e.toString() }
            finally { _busy.value = false }
        }
    }

    fun patch(field: String, value: kotlinx.serialization.json.JsonElement) = change {
        IrisLink.api().send("PATCH", "/user/analysis", JsonObject(mapOf(field to value)).toString(),
            AnalysisPreferences.serializer())
    }

    fun toggleEngine(engine: String) {
        val prefs = _analysis.value ?: return
        val current = prefs.enabledEngines ?: prefs.availableEngines
        val next = if (engine in current) current.filterNot { it == engine } else current + engine
        patch("enabledEngines", kotlinx.serialization.json.JsonArray(next.map(::JsonPrimitive)))
    }

    fun reset() = change { IrisLink.api().send("POST", "/user/analysis/reset", null, AnalysisPreferences.serializer()) }

    private fun change(request: suspend () -> AnalysisPreferences) {
        if (_busy.value) return
        viewModelScope.launch {
            _busy.value = true
            try {
                _analysis.value = request()
                refreshAnalysis()
            } catch (e: Exception) { _error.value = e.message ?: e.toString() }
            finally { _busy.value = false }
        }
    }

    fun clearError() { _error.value = null }
}

@Composable
fun SettingsScreen(onNavigate: (String) -> Unit) {
    val model: SettingsViewModel = viewModel()
    val facts by model.facts.collectAsState()
    val analysis by model.analysis.collectAsState()
    val refreshing by model.refreshing.collectAsState()
    val busy by model.busy.collectAsState()
    val confirmFact by model.confirmFact.collectAsState()
    val error by model.error.collectAsState()
    val context = LocalContext.current
    val colors = LocalIrisColors.current
    var sliderValue by remember(analysis?.maxItems) { mutableIntStateOf(analysis?.maxItems ?: 1) }
    LaunchedEffect(model) { model.refresh() }
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(error) {
        if (error != null) {
            snackbar.showSnackbar(error.orEmpty())
            model.clearError()
        }
    }
    if (confirmFact != null) ConfirmDialog(
        text = "Stop counting this confirmed pattern? Its occurrences are removed and it will not be proposed again.",
        confirmLabel = "stop counting", onConfirm = model::confirmForget, onDismiss = model::cancelForget,
    )
    val title = buildAnnotatedString {
        append("The shape of you, ")
        withStyle(SpanStyle(color = colors.sage, fontStyle = FontStyle.Italic)) { append("so far.") }
    }
    IrisScaffold(title = title, kicker = "settings · what iris knows", snackbarHostState = snackbar) { padding ->
        RefreshableList(refreshing, model::refresh) {
            LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = androidx.compose.foundation.layout.PaddingValues(
                start = 20.dp, end = 20.dp, bottom = 36.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                when (val state = facts) {
                    Loadable.Loading -> item { LoadingState("Iris is gathering what she knows…") }
                    is Loadable.Failed -> item { ErrorState(onRetry = model::refresh) }
                    is Loadable.Ready -> {
                        item { Kicker("iris's stable notes about you") }
                        items(state.value, key = { it.id }) { fact ->
                            Column {
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                    Column(Modifier.weight(1f)) {
                                        Text("\"${fact.fact}\"", fontFamily = Serif, fontSize = 17.sp, fontStyle = FontStyle.Italic,
                                            color = colors.ink)
                                        Text("${fact.source}     ${fact.ageDays}d", fontSize = 10.sp, color = colors.ink3)
                                    }
                                    if (fact.editable) IconButton(onClick = { model.requestForget(fact) }, enabled = !busy) {
                                        Icon(painterResource(R.drawable.ic_close),
                                            contentDescription = if (fact.source == "confirmed") "stop counting" else "forget",
                                            tint = colors.rose)
                                    }
                                }
                                HorizontalDivider(color = colors.lineSoft)
                            }
                        }
                        if (analysis != null) item {
                            val prefs = analysis!!
                            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                                Kicker("what iris is willing to say")
                                Text("These decide which observations reach a conversation at all. They are not about tone — a finding held back here is one Iris does not consider well-enough evidenced to raise.",
                                    fontStyle = FontStyle.Italic, color = colors.ink3)
                                Kicker("minimum confidence")
                                val levels = listOf("low", "medium", "high")
                                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                                    levels.forEachIndexed { index, level ->
                                        SegmentedButton(
                                            selected = prefs.minConfidence == level,
                                            onClick = { model.patch("minConfidence", JsonPrimitive(level)) },
                                            enabled = !busy,
                                            shape = SegmentedButtonDefaults.itemShape(index, levels.size),
                                        ) { Text(level) }
                                    }
                                }
                                Kicker("most observations at once · $sliderValue")
                                Slider(value = sliderValue.toFloat(), onValueChange = { sliderValue = it.toInt().coerceIn(1, 10) },
                                    onValueChangeFinished = {
                                        if (sliderValue != prefs.maxItems) model.patch("maxItems", JsonPrimitive(sliderValue))
                                    }, valueRange = 1f..10f, steps = 8, enabled = !busy)
                                Kicker("what she looks for")
                                prefs.availableEngines.forEach { engine ->
                                    val checked = engine in (prefs.enabledEngines ?: prefs.availableEngines)
                                    Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                                        Checkbox(checked = checked, onCheckedChange = { model.toggleEngine(engine) }, enabled = !busy)
                                        Text(engineLabels[engine] ?: engine,
                                            color = if (checked) colors.ink else colors.ink4, modifier = Modifier.weight(1f))
                                    }
                                }
                                TextButton(onClick = model::reset, enabled = !busy) { Text("restore defaults") }
                            }
                        }
                        item {
                            IrisCard {
                                Kicker("Android live sensors")
                                Text("The Android app collects permitted readings and sends them to IRIS automatically. They appear in Sensors for review; nothing becomes evidence until you link it.", color = colors.ink2)
                                Text("Paired with ${Settings.laptopBaseUrl(context)}", color = colors.ink2)
                                OutlinedButton(onClick = { onNavigate("collector") }) { Text("Open Phone collector") }
                            }
                        }
                        item {
                            IrisCard {
                                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    IrisOrb(14.dp)
                                    Kicker("iris's note")
                                }
                                Text("\"Everything I know about you is stored on this machine, in your own Postgres — nothing is kept anywhere else. What you write is sent to OpenAI to be turned into embeddings and replies, and nowhere else. Every note above is something I inferred from your own words; remove any of them with the ×, and it's gone.\"",
                                    fontFamily = Serif, fontSize = 15.sp, fontStyle = FontStyle.Italic, color = colors.ink2)
                            }
                        }
                    }
                }
            }
        }
    }
}
