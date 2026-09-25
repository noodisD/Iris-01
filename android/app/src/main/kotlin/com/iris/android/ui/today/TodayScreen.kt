package com.iris.android.ui.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
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
import com.iris.android.api.HabitsTodayResponse
import com.iris.android.api.InsightSummary
import com.iris.android.api.IrisLink
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisOrb
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
import kotlinx.coroutines.supervisorScope
import kotlinx.serialization.builtins.ListSerializer

class TodayViewModel : ViewModel() {
    private val _habits = MutableStateFlow<Loadable<HabitsTodayResponse>>(Loadable.Loading)
    val habits = _habits.asStateFlow()
    private val _insights = MutableStateFlow<Loadable<List<InsightSummary>>>(Loadable.Loading)
    val insights = _insights.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private var habitsVersion = 0
    private var insightsVersion = 0

    fun refresh() {
        viewModelScope.launch {
            _refreshing.value = true
            try {
                supervisorScope {
                    launch { fetchHabits() }
                    launch { fetchInsights() }
                }
            } finally {
                _refreshing.value = false
            }
        }
    }

    fun retryHabits() { viewModelScope.launch { fetchHabits() } }
    fun retryInsights() { viewModelScope.launch { fetchInsights() } }

    private suspend fun fetchHabits() {
        val version = ++habitsVersion
        try {
            val result = IrisLink.api().send("GET", "/habits/today", null, HabitsTodayResponse.serializer())
            if (version == habitsVersion) _habits.value = Loadable.Ready(result)
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) { if (version == habitsVersion) _habits.value = Loadable.Failed(e.message ?: "Habits didn't load.") }
    }

    private suspend fun fetchInsights() {
        val version = ++insightsVersion
        try {
            val result = IrisLink.api().send("GET", "/insights", null, ListSerializer(InsightSummary.serializer()))
            if (version == insightsVersion) _insights.value = Loadable.Ready(result)
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) { if (version == insightsVersion) _insights.value = Loadable.Failed(e.message ?: "Findings didn't load.") }
    }
}

@Composable
fun TodayScreen(onNavigate: (String) -> Unit) {
    val vm: TodayViewModel = viewModel()
    val habits by vm.habits.collectAsState()
    val insights by vm.insights.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val colors = LocalIrisColors.current
    LaunchedEffect(Unit) { vm.refresh() }
    val title = buildAnnotatedString {
        append("Today's reading")
        withStyle(SpanStyle(color = colors.sage)) { append(".") }
    }
    IrisScaffold(title = title, kicker = "today · at a glance") { padding ->
        RefreshableList(refreshing, vm::refresh) {
            LazyColumn(
                Modifier.fillMaxSize().padding(padding),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 32.dp),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                if (habits is Loadable.Loading || insights is Loadable.Loading) {
                    item { LoadingState() }
                } else if (habits is Loadable.Failed && insights is Loadable.Failed) {
                    item { ErrorState(onRetry = vm::refresh) }
                } else {
                    item { Button(onClick = { onNavigate("chat") }, modifier = Modifier.fillMaxWidth()) { Text("▷ Daily check-in") } }
                    val featured = (insights as? Loadable.Ready)?.value?.firstOrNull { it.featured }
                    if (featured != null) item {
                        IrisCard(Modifier.fillMaxWidth(), onClick = { onNavigate("insights/${featured.id}") }) {
                            Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.Top) {
                                IrisOrb()
                                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Kicker("iris · ${featured.kind}")
                                    Text("\"${featured.summary}\"", fontFamily = Serif, fontStyle = FontStyle.Italic,
                                        fontSize = 22.sp, color = colors.ink, lineHeight = 29.sp)
                                }
                                TextButton(onClick = { onNavigate("insights/${featured.id}") }) { Text("↗ open") }
                            }
                        }
                    }
                    if (insights is Loadable.Failed) item { Unavailable("Findings", vm::retryInsights) }
                    if (habits is Loadable.Failed) item { Unavailable("Habits", vm::retryHabits) }
                    val today = (habits as? Loadable.Ready)?.value
                    if (today != null) item {
                        IrisCard(Modifier.fillMaxWidth()) {
                            Kicker("Habits · today")
                            Row(verticalAlignment = Alignment.Bottom, modifier = Modifier.padding(top = 10.dp)) {
                                Text("${today.doneCount}", fontFamily = Serif, fontSize = 56.sp, color = colors.ink, lineHeight = 58.sp)
                                Text("/${today.totalCount}", Modifier.padding(start = 6.dp, bottom = 8.dp), fontSize = 12.sp, color = colors.ink3)
                            }
                            Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                today.habits.take(4).forEach { habit ->
                                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Spacer(Modifier.size(10.dp).background(if (habit.doneToday) colors.sage else colors.line, CircleShape))
                                        Text(habit.name, fontSize = 12.sp, color = if (habit.doneToday) colors.ink else colors.ink3)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Unavailable(what: String, retry: () -> Unit) {
    val colors = LocalIrisColors.current
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("$what didn't load. Nothing is lost — this is only the view.", Modifier.weight(1f),
            fontSize = 13.sp, color = colors.ink3)
        TextButton(onClick = retry) { Text("retry", style = IrisType.mono) }
    }
}
