package com.iris.android.ui.sensors

import androidx.compose.foundation.text.ClickableText
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.IrisLink
import com.iris.android.api.SensorBatch
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.EmptyState
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.theme.LocalIrisColors
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.ListSerializer
import java.text.DateFormat
import java.time.Instant
import java.time.OffsetDateTime
import java.util.Date

internal fun sensorSourceLabel(source: String): String = when (source) {
    "pixel" -> "Pixel"
    "health_connect" -> "Health Connect"
    else -> source
}

internal fun sensorLocalDate(value: String): String = sensorDate(value, DateFormat.getDateInstance())
internal fun sensorLocalTime(value: String): String = sensorDate(value, DateFormat.getTimeInstance())
internal fun sensorLocalDateTime(value: String): String = sensorDate(value, DateFormat.getDateTimeInstance())
private fun sensorDate(value: String, formatter: DateFormat): String = runCatching {
    val instant = runCatching { Instant.parse(value) }.getOrElse { OffsetDateTime.parse(value).toInstant() }
    formatter.format(Date.from(instant))
}.getOrDefault(value)

internal class SensorsViewModel : ViewModel() {
    private val _batches = MutableStateFlow<Loadable<List<SensorBatch>>>(Loadable.Loading)
    val batches = _batches.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()

    fun refresh() {
        if (_refreshing.value) return
        viewModelScope.launch {
            _refreshing.value = true
            try {
                _batches.value = Loadable.Ready(IrisLink.api().send("GET", "/sensors/batches", null,
                    ListSerializer(SensorBatch.serializer())))
            } catch (error: Exception) {
                _batches.value = Loadable.Failed(error.message ?: error.toString())
            } finally {
                _refreshing.value = false
            }
        }
    }
}

@Composable
fun SensorsScreen(onNavigate: (String) -> Unit) {
    val model: SensorsViewModel = viewModel()
    val batches by model.batches.collectAsState()
    val refreshing by model.refreshing.collectAsState()
    val colors = LocalIrisColors.current
    LaunchedEffect(model) {
        model.refresh()
        while (true) {
            delay(30_000)
            model.refresh()
        }
    }
    IrisScaffold(title = "Your measurements", kicker = "sensors · review before linking") { padding ->
        RefreshableList(refreshing, model::refresh) {
            LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = androidx.compose.foundation.layout.PaddingValues(
                start = 20.dp, end = 20.dp, bottom = 28.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    val intro = buildAnnotatedString {
                        append("Readings arrive as one batch per source per day. Review a day's batch before linking any measurements to a theme. ")
                        pushStringAnnotation("destination", "settings")
                        withStyle(SpanStyle(color = colors.sage, textDecoration = TextDecoration.Underline)) {
                            append("Pair the phone in Settings")
                        }
                        pop()
                        append(".")
                    }
                    ClickableText(intro, modifier = Modifier.padding(top = 12.dp),
                        style = androidx.compose.material3.MaterialTheme.typography.bodyMedium.copy(color = colors.ink2),
                        onClick = { position ->
                            if (intro.getStringAnnotations("destination", position, position).isNotEmpty()) onNavigate("settings")
                        })
                }
                item { Kicker("staged batches") }
                when (val state = batches) {
                    Loadable.Loading -> item { LoadingState("Loading sensor batches…") }
                    is Loadable.Failed -> item { ErrorState(state.message, model::refresh) }
                    is Loadable.Ready -> {
                        if (state.value.isEmpty()) item {
                            EmptyState("No sensor data", "Pair the Android app and start live collection; new readings will appear here.")
                        }
                        items(state.value, key = { it.id }) { batch ->
                            Column {
                                ListItem(
                                    headlineContent = {
                                        Text("${sensorSourceLabel(batch.source)} · ${batch.review_day ?: sensorLocalDate(batch.received_at)}")
                                    },
                                    supportingContent = {
                                        Text("${batch.status} · ${batch.observation_count} readings" +
                                            (batch.last_delivery_at?.let { " · last delivery ${sensorLocalTime(it)}" } ?: ""))
                                    },
                                    modifier = Modifier.fillMaxWidth().clickable { onNavigate("sensors/${batch.id}") },
                                    colors = androidx.compose.material3.ListItemDefaults.colors(containerColor = colors.bg0),
                                )
                                HorizontalDivider(color = colors.lineSoft)
                            }
                        }
                    }
                }
            }
        }
    }
}
