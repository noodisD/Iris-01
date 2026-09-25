@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class, androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.iris.android.ui.insights

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.R
import com.iris.android.api.InsightDetail
import com.iris.android.api.InsightSummary
import com.iris.android.api.IrisLink
import com.iris.android.ui.DAY_WITH_WEEKDAY
import com.iris.android.ui.Loadable
import com.iris.android.ui.formatEventDate
import com.iris.android.ui.components.EmptyState
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisOrb
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.components.Tag
import com.iris.android.ui.components.TwinSeriesChart
import com.iris.android.ui.habits.habitColor
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import com.iris.android.api.json

class InsightDetailViewModel : ViewModel() {
    private val _detail = MutableStateFlow<Loadable<InsightDetail?>>(Loadable.Loading)
    val detail = _detail.asStateFlow()
    private val _acting = MutableStateFlow<String?>(null)
    val acting = _acting.asStateFlow()
    private val _actionError = MutableStateFlow<String?>(null)
    val actionError = _actionError.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private var loadedId: String? = null

    fun refresh(id: String) {
        viewModelScope.launch {
            if (_refreshing.value) return@launch
            if (loadedId != id) { loadedId = id; _detail.value = Loadable.Loading }
            _refreshing.value = true
            try {
                _detail.value = Loadable.Ready(IrisLink.api().send("GET", "/insights/${Uri.encode(id)}", null, InsightDetail.serializer()))
            } catch (e: com.iris.android.api.IrisApiException) {
                _detail.value = Loadable.Failed(e.message)
            } catch (e: Exception) {
                _detail.value = Loadable.Failed(e.message ?: "Iris couldn't reach your data just now.")
            } finally {
                _refreshing.value = false
            }
        }
    }

    fun act(id: String, kind: String, onSuccess: () -> Unit) {
        viewModelScope.launch {
            if (_acting.value != null) return@launch
            _acting.value = kind
            _actionError.value = null
            try {
                IrisLink.api().send("POST", "/insights/${Uri.encode(id)}/${if (kind == "snooze") "snooze" else "resolve"}",
                    if (kind == "snooze") json.encodeToString(mapOf("days" to 30)) else null, InsightSummary.serializer())
                onSuccess()
            } catch (e: Exception) {
                _actionError.value = e.message ?: e.toString()
            } finally {
                _acting.value = null
            }
        }
    }
}

@Composable
fun InsightDetailScreen(id: String, onNavigate: (String) -> Unit, onBack: () -> Unit, onDecisionDone: () -> Unit) {
    val vm: InsightDetailViewModel = viewModel()
    val state by vm.detail.collectAsState()
    val acting by vm.acting.collectAsState()
    val actionError by vm.actionError.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val colors = LocalIrisColors.current
    LaunchedEffect(id) { vm.refresh(id) }
    Scaffold(topBar = {
        TopAppBar(title = { Kicker((state as? Loadable.Ready)?.value?.kind ?: "insights") },
            navigationIcon = {
                IconButton(onClick = onBack) {
                    Icon(painterResource(R.drawable.ic_arrow_back), contentDescription = "← all insights")
                }
            }, colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.bg0))
    }, containerColor = colors.bg0) { padding ->
        RefreshableList(refreshing, { vm.refresh(id) }) {
            LazyColumn(Modifier.fillMaxWidth().padding(padding),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(24.dp)) {
                when (val s = state) {
                    is Loadable.Loading -> item { LoadingState() }
                    is Loadable.Failed -> item { ErrorState(onRetry = { vm.refresh(id) }) }
                    is Loadable.Ready -> {
                        val detail = s.value
                        if (detail == null) item {
                            ErrorState(onRetry = { vm.refresh(id) })
                        } else {
                            item {
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    FilledTonalButton(onClick = {
                                        val draft = "About what you noticed — \"${detail.headline.line1}\": "
                                        onNavigate("chat?draft=${Uri.encode(draft)}")
                                    }) { Text("▷ ask iris about this") }
                                    OutlinedButton(onClick = { vm.act(id, "snooze", onDecisionDone) }, enabled = acting == null) {
                                        Text(if (acting == "snooze") "snoozing…" else "snooze 30d")
                                    }
                                    OutlinedButton(onClick = { vm.act(id, "resolve", onDecisionDone) }, enabled = acting == null) {
                                        Text(if (acting == "resolve") "resolving…" else "mark resolved")
                                    }
                                }
                                if (actionError != null) Text(actionError!!, Modifier.padding(top = 10.dp),
                                    color = colors.rose, style = IrisType.mono)
                            }
                            item {
                                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                        if (detail.featured) Tag("★ featured", colors.sage)
                                        InsightProvenance(detail.origin, detail.claimKind)
                                        detail.tags.forEach { Tag(it) }
                                    }
                                    InsightHeadline(detail.headline, habitColor(detail.accentColor), 44)
                                    Text(detail.summary, fontFamily = Serif, fontSize = 17.sp,
                                        lineHeight = 26.sp, color = colors.ink2)
                                }
                            }
                            val twin = detail.evidence.firstOrNull { it.kind == "twin-series" }
                            if (twin != null) item {
                                Column {
                                    Kicker(twin.label.orEmpty())
                                    Text("The evidence.", Modifier.padding(vertical = 10.dp), fontFamily = Serif,
                                        fontSize = 24.sp, color = colors.ink)
                                    TwinSeriesChart(twin.series.orEmpty())
                                }
                            }
                            val comp = detail.evidence.firstOrNull { it.kind == "comparison" }
                            if (comp != null) item {
                                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                    Kicker(comp.label.orEmpty())
                                    FlowRow(horizontalArrangement = Arrangement.spacedBy(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                        comp.items.orEmpty().forEachIndexed { index, value ->
                                            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                                Row {
                                                    Text("${if (index == 0 && value.value > 0) "+" else ""}${formatComparison(value.value)}",
                                                        fontFamily = Serif, fontSize = 56.sp,
                                                        color = if (index == 0) habitColor(detail.accentColor) else colors.ink)
                                                    if (value.sub != null) Text(value.sub, Modifier.padding(start = 4.dp),
                                                        fontSize = 16.sp, color = colors.ink3)
                                                }
                                                Kicker(value.label)
                                            }
                                        }
                                    }
                                }
                            }
                            item {
                                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                                    Kicker("in your own words")
                                    Text("Pull quotes.", fontFamily = Serif, fontSize = 24.sp, color = colors.ink)
                                    detail.pullQuotes.forEach { quote ->
                                        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
                                            Spacer(Modifier.width(2.dp).fillMaxHeight().background(habitColor(detail.accentColor)))
                                            Column(Modifier.weight(1f).padding(start = 16.dp)) {
                                                Text("\"${quote.text}\"", fontFamily = Serif, fontStyle = FontStyle.Italic,
                                                    fontSize = 18.sp, lineHeight = 26.sp, color = colors.ink)
                                                val citation = "${formatEventDate(quote.sourceDate)} · ${quote.sourceKind}"
                                                if (quote.sourceId != null) TextButton(
                                                    onClick = { onNavigate("journal?entry=${Uri.encode(quote.sourceId)}") },
                                                    contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) {
                                                    Text("$citation · read the entry ↗", color = habitColor(detail.accentColor), style = IrisType.mono)
                                                } else Kicker(citation)
                                            }
                                        }
                                    }
                                }
                            }
                            item {
                                IrisCard(Modifier.fillMaxWidth()) {
                                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) { IrisOrb(14.dp); Kicker("iris's read") }
                                    Text("\"${detail.irisRead}\"", Modifier.padding(top = 10.dp), fontFamily = Serif,
                                        fontStyle = FontStyle.Italic, fontSize = 18.sp, lineHeight = 25.sp, color = colors.ink)
                                }
                            }
                            if (detail.related.isNotEmpty()) item {
                                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Kicker("related")
                                    detail.related.forEach { related ->
                                        Row(Modifier.fillMaxWidth().clickable { onNavigate("insights/${related.id}") },
                                            horizontalArrangement = Arrangement.SpaceBetween) {
                                            Text(related.label, color = colors.ink2, fontSize = 13.sp)
                                            Tag(related.tag)
                                        }
                                    }
                                }
                            }
                            item {
                                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Kicker("how iris found this")
                                    Text(detail.methodology, fontSize = 11.sp, fontStyle = FontStyle.Italic,
                                        color = colors.ink3, lineHeight = 18.sp)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun formatComparison(value: Double): String =
    if (value.isFinite() && value == value.toLong().toDouble()) value.toLong().toString() else value.toString()
