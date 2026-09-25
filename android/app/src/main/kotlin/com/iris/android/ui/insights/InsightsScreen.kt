@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.iris.android.ui.insights

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
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
import com.iris.android.api.InsightCoverage
import com.iris.android.api.InsightSummary
import com.iris.android.api.IrisLink
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.EmptyState
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.components.Tag
import com.iris.android.ui.formatEventDate
import com.iris.android.ui.DAY_LONG
import com.iris.android.ui.habits.habitColor
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.ListSerializer

class InsightsViewModel : ViewModel() {
    private val _insights = MutableStateFlow<Loadable<List<InsightSummary>>>(Loadable.Loading)
    val insights = _insights.asStateFlow()
    private val _coverage = MutableStateFlow<InsightCoverage?>(null)
    val coverage = _coverage.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            if (_refreshing.value) return@launch
            _refreshing.value = true
            try {
                val list = IrisLink.api().send("GET", "/insights", null, ListSerializer(InsightSummary.serializer()))
                _insights.value = Loadable.Ready(list)
                _coverage.value = if (list.isEmpty()) {
                    try { IrisLink.api().send("GET", "/insights/coverage", null, InsightCoverage.serializer()) }
                    catch (_: Exception) { null } // A failed coverage check must not claim an absence.
                } else null
            } catch (e: Exception) {
                _insights.value = Loadable.Failed(e.message ?: "Iris couldn't reach your data just now.")
            } finally {
                _refreshing.value = false
            }
        }
    }
}

@Composable
fun InsightsScreen(onNavigate: (String) -> Unit) {
    val vm: InsightsViewModel = viewModel()
    val state by vm.insights.collectAsState()
    val coverage by vm.coverage.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val colors = LocalIrisColors.current
    LaunchedEffect(Unit) { vm.refresh() }
    val list = (state as? Loadable.Ready)?.value.orEmpty()
    val title = buildAnnotatedString {
        append("${list.size} patterns, ")
        withStyle(SpanStyle(fontStyle = FontStyle.Italic, color = colors.sage)) {
            append("${list.count { !it.seen }} new.")
        }
    }
    IrisScaffold(title = title, kicker = "insights · what iris has noticed") { padding ->
        RefreshableList(refreshing, vm::refresh) {
            LazyColumn(Modifier.fillMaxWidth().padding(padding), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)) {
                when (val s = state) {
                    is Loadable.Loading -> item { LoadingState("Iris is reviewing your patterns…") }
                    is Loadable.Failed -> item { ErrorState(onRetry = vm::refresh) }
                    is Loadable.Ready -> if (s.value.isEmpty()) {
                        item { EmptyInsights(coverage) }
                    } else {
                        items(s.value, key = { it.id }) { insight ->
                            InsightCard(insight) { onNavigate("insights/${insight.id}") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun InsightCard(insight: InsightSummary, onOpen: () -> Unit) {
    val colors = LocalIrisColors.current
    val accent = habitColor(insight.accentColor)
    Card(onClick = onOpen, modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = if (insight.featured) colors.sage.copy(alpha = 0.04f) else colors.bg2),
        border = BorderStroke(1.dp, if (insight.featured) colors.sageDim else colors.lineSoft)) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Kicker(insight.kind, color = accent)
                    if (insight.featured) Tag("★ featured", colors.sage)
                }
                if (!insight.seen) Canvas(Modifier.size(6.dp)) { drawCircle(colors.sage) }
            }
            InsightHeadline(insight.headline, accent, if (insight.featured) 34 else 28)
            Text(insight.summary, color = colors.ink3, fontSize = 13.sp, lineHeight = 20.sp)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                InsightProvenance(insight.origin, insight.claimKind)
                insight.tags.forEach { Tag(it) }
            }
            Text("open ↗", style = IrisType.mono, color = accent)
        }
    }
}

@Composable
internal fun InsightHeadline(headline: com.iris.android.api.InsightHeadline, accent: Color, size: Int) {
    val colors = LocalIrisColors.current
    Column {
        Text(headline.line1, fontFamily = Serif, fontSize = size.sp, lineHeight = size.sp, color = colors.ink)
        Text(headline.line2, fontFamily = Serif, fontSize = size.sp, lineHeight = size.sp, color = accent)
        Text(headline.line3, fontFamily = Serif, fontSize = size.sp, lineHeight = size.sp,
            fontStyle = FontStyle.Italic, color = colors.ink2)
    }
}

@Composable
internal fun InsightProvenance(origin: String?, claimKind: String?) {
    if (origin == "observed") Tag("confirmed · ${if (claimKind == "behaviour") "behaviour" else "mentions in writing"}")
}

@Composable
private fun EmptyInsights(c: InsightCoverage?) {
    if (c == null || c.entries == 0) {
        EmptyState("No patterns yet.", "Iris needs about a week of conversations and entries before she'll surface anything. She won't guess.")
        return
    }
    val held = "Your ${c.entries} entries are still here, ${c.entriesInThemes} of them grouped into ${c.themes} themes."
    val days = "${c.observedDaysInWindow} day${if (c.observedDaysInWindow == 1) "" else "s"}"
    when {
        !c.available -> EmptyState("Iris can't tell right now.", "The check for how much you've written recently didn't answer, so nothing is being claimed about how things are. $held")
        c.observedDaysInWindow == 0 && c.lastEntryOn != null -> EmptyState("Nothing written since ${formatEventDate(c.lastEntryOn, DAY_LONG)}.",
            "Patterns about now are measured over the last ${c.windowDays} days, and nothing falls in them — so Iris has nothing to say about how things are. $held They come back the moment you write again.")
        !c.supportsCurrentState -> EmptyState("Not enough written lately.",
            "Describing how things are now takes ${c.observedDaysRequired} days of writing in the last ${c.windowDays}, and there ${if (c.observedDaysInWindow == 1) "is" else "are"} $days. One entry after a long gap is a sign of life, not a basis for saying how you are. $held")
        (c.suppressedByFilter ?: 0) > 0 -> EmptyState("Hidden by your settings.",
            "Iris has ${c.suppressedByFilter} observation${if (c.suppressedByFilter == 1) "" else "s"} that your confidence filter removes. That is your filter working, not an absence of patterns — Settings will show them.")
        c.admitted != null && c.admitted > 0 && c.hiddenByStatus == c.admitted -> EmptyState("All caught up.",
            "Iris found ${c.admitted} pattern${if (c.admitted == 1) "" else "s"}, and you have marked ${if (c.admitted == 1) "it" else "them all"} resolved or snoozed. $held")
        else -> EmptyState("Nothing measurable about now.", "$days of writing in the last ${c.windowDays}, and nothing has recurred often enough to measure against it. $held")
    }
}
