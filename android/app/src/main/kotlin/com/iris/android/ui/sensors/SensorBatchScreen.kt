@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.iris.android.ui.sensors

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.IrisApiException
import com.iris.android.api.IrisLink
import com.iris.android.api.KnownFact
import com.iris.android.api.SensorBatch
import com.iris.android.api.SensorObservation
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.EmptyState
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.theme.LocalIrisColors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime

private const val PAGE_SIZE = 100
private val units = mapOf(
    "pixel_steps" to "steps", "pixel_app_usage" to "seconds foreground",
    "health_connect_heart_rate" to "bpm", "health_connect_sleep" to "minutes asleep",
    "health_connect_spo2" to "%",
)

internal class SensorBatchViewModel : ViewModel() {
    private val _batch = MutableStateFlow<Loadable<SensorBatch>>(Loadable.Loading)
    val batch = _batch.asStateFlow()
    private val _themes = MutableStateFlow<Loadable<List<KnownFact>>>(Loadable.Loading)
    val themes = _themes.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private val _links = MutableStateFlow<Map<String, Long?>>(emptyMap())
    val links = _links.asStateFlow()
    private val _action = MutableStateFlow<String?>(null)
    val action = _action.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error = _error.asStateFlow()
    private val _stale = MutableStateFlow(false)
    val stale = _stale.asStateFlow()
    private var initialized = false

    fun refresh(id: Long) {
        if (_refreshing.value) return
        viewModelScope.launch {
            _refreshing.value = true
            try {
                val api = IrisLink.api()
                val fresh = api.send("GET", "/sensors/batches/$id", null, SensorBatch.serializer())
                _batch.value = Loadable.Ready(fresh)
                if (!initialized) {
                    initialized = true
                    _links.value = if (fresh.theme_links.isNotEmpty()) fresh.theme_links else runCatching {
                        val all = api.send("GET", "/sensors/batches", null, ListSerializer(SensorBatch.serializer()))
                        val suggested = all.firstOrNull { it.source == fresh.source && it.status == "confirmed" }?.theme_links.orEmpty()
                        val types = fresh.parsed_payload?.observations.orEmpty().map { it.source_type }.toSet()
                        suggested.filterKeys { it in types }
                    }.getOrDefault(emptyMap())
                }
            } catch (e: Exception) {
                _batch.value = Loadable.Failed(e.message ?: e.toString())
            } finally {
                _refreshing.value = false
            }
            refreshThemes()
        }
    }

    fun refreshThemes() {
        viewModelScope.launch {
            try {
                _themes.value = Loadable.Ready(IrisLink.api().send("GET", "/knowledge", null,
                    ListSerializer(KnownFact.serializer())))
            } catch (e: Exception) {
                _themes.value = Loadable.Failed(e.message ?: e.toString())
            }
        }
    }

    fun setLink(type: String, id: Long?) { _links.value = _links.value + (type to id) }

    fun confirm(id: Long) = act("confirm", id)
    fun reject(id: Long) = act("reject", id)
    fun delete(id: Long, onDeleted: () -> Unit) = act("delete", id, onDeleted)

    private fun act(kind: String, id: Long, onDeleted: (() -> Unit)? = null) {
        if (_action.value != null) return
        val current = (_batch.value as? Loadable.Ready)?.value ?: return
        val known = (_themes.value as? Loadable.Ready)?.value ?: emptyList()
        val knownIds = known.mapNotNull { it.id.toLongOrNull() }.toSet()
        val links = current.parsed_payload?.observations.orEmpty().map { it.source_type }.distinct()
            .associateWith { type -> _links.value[type]?.takeIf { it in knownIds } }
        viewModelScope.launch {
            _action.value = kind
            _error.value = null
            try {
                when (kind) {
                    "confirm" -> {
                        val body = JsonObject(mapOf(
                            "links" to JsonObject(links.mapValues { (_, theme) -> theme?.let { JsonPrimitive(it) } ?: JsonNull }),
                            "observation_count" to JsonPrimitive(current.observation_count),
                        ))
                        _batch.value = Loadable.Ready(IrisLink.api().send("POST", "/sensors/batches/$id/confirm",
                            body.toString(), SensorBatch.serializer()))
                        _stale.value = false
                    }
                    "reject" -> _batch.value = Loadable.Ready(IrisLink.api().send("POST", "/sensors/batches/$id/reject",
                        null, SensorBatch.serializer()))
                    "delete" -> {
                        IrisLink.api().send("DELETE", "/sensors/batches/$id", null, Unit.serializer())
                        onDeleted?.invoke()
                    }
                }
            } catch (e: Exception) {
                if (kind == "confirm" && e is IrisApiException && e.status == 409) {
                    _stale.value = true
                    refresh(id)
                } else _error.value = "Request failed: ${e.message ?: e}"
            } finally {
                _action.value = null
            }
        }
    }
}

private fun readableSensorDate(value: String?): Boolean = value != null && runCatching {
    if (Regex("^\\d{4}-\\d{2}-\\d{2}$").matches(value)) LocalDate.parse(value)
    else runCatching { Instant.parse(value) }.getOrElse { OffsetDateTime.parse(value).toInstant() }
}.isSuccess

private fun observationDescription(reading: SensorObservation): String {
    val unit = units[reading.source_type]
    val numeric = reading.value_num?.let {
        val n = if (it % 1.0 == 0.0) it.toLong().toString() else it.toString()
        n + when (unit) { "%" -> "%"; null -> ""; else -> " $unit" }
    }
    val location = if (reading.lat != null || reading.lon != null)
        "latitude ${reading.lat?.toString() ?: "unknown"}, longitude ${reading.lon?.toString() ?: "unknown"}" else null
    return listOfNotNull(numeric, reading.value_text?.takeIf { it.isNotEmpty() }, location,
        reading.origin_package?.let { "Health Connect writer: $it" }).joinToString(" · ").ifEmpty { "No value recorded" }
}

@Composable
fun SensorBatchScreen(id: Long, onBack: () -> Unit) {
    val model: SensorBatchViewModel = viewModel()
    val batch by model.batch.collectAsState()
    val themes by model.themes.collectAsState()
    val links by model.links.collectAsState()
    val action by model.action.collectAsState()
    val error by model.error.collectAsState()
    val stale by model.stale.collectAsState()
    val refreshing by model.refreshing.collectAsState()
    val colors = LocalIrisColors.current
    val pages = remember(id) { mutableStateMapOf<String, Int>() }
    LaunchedEffect(id) { model.refresh(id) }
    val title = (batch as? Loadable.Ready)?.value?.let { "Review ${sensorSourceLabel(it.source)} readings" } ?: "Your measurements"
    IrisScaffold(title = title, kicker = "sensors", onBack = onBack) { padding ->
        RefreshableList(refreshing, { model.refresh(id) }) {
            LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = androidx.compose.foundation.layout.PaddingValues(
                start = 20.dp, end = 20.dp, bottom = 40.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                when (val state = batch) {
                    Loadable.Loading -> item { LoadingState("Loading measurements…") }
                    is Loadable.Failed -> item { ErrorState(state.message, { model.refresh(id) }) }
                    is Loadable.Ready -> {
                        val current = state.value
                        val groups = current.parsed_payload?.observations.orEmpty().groupBy { it.source_type }
                        val undated = groups.values.flatten().count { !readableSensorDate(it.occurred_at) }
                        val known = (themes as? Loadable.Ready)?.value.orEmpty()
                        val knownIds = known.mapNotNull { it.id.toLongOrNull() }.toSet()
                        item {
                            Text("Received ${sensorLocalDateTime(current.received_at)} · ${current.observation_count} readings · ${current.dropped_count} dropped",
                                color = colors.ink3)
                        }
                        if (current.status == "pending" && current.theme_links.isEmpty() && links.isNotEmpty()) item {
                            Text("Links prefilled from your last confirmed ${sensorSourceLabel(current.source)} batch.", color = colors.ink2)
                        }
                        if (current.status != "pending") item {
                            IrisCard { Text("This batch is ${current.status}.", color = colors.ink2) }
                        }
                        if (current.dropped_count > 0) item {
                            SensorNotice("${current.dropped_count} readings were dropped while parsing this batch.", colors.amber)
                        }
                        if (undated > 0) item {
                            SensorNotice("$undated ${if (undated == 1) "reading has" else "readings have"} no readable date. Check these before linking.", colors.amber)
                        }
                        current.clock_skew_seconds?.takeIf { kotlin.math.abs(it) >= 120 }?.let { skew -> item {
                            SensorNotice("Device clock skew detected: ${if (skew > 0) "+" else ""}${if (skew % 1.0 == 0.0) skew.toLong() else skew} seconds. Check reading times against your device.", colors.amber)
                        } }
                        item { Kicker("observations by source") }
                        when (val result = themes) {
                            Loadable.Loading -> item { Text("Loading existing themes…", color = colors.ink3) }
                            is Loadable.Failed -> item {
                                Row { Text("Could not load themes: ${result.message}", color = colors.rose)
                                    TextButton(onClick = model::refreshThemes) { Text("Try again") } }
                            }
                            else -> Unit
                        }
                        if (groups.isEmpty()) item {
                            EmptyState("No readable measurements", "This batch has no observations to link.")
                        }
                        groups.forEach { (sourceType, readings) ->
                            item(key = sourceType) {
                                IrisCard(Modifier.fillMaxWidth()) {
                                Column(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                    Text("$sourceType (${readings.size} readings)", color = colors.ink)
                                    readings.take(pages[sourceType] ?: PAGE_SIZE).forEach { reading ->
                                        HorizontalDivider(color = colors.lineSoft)
                                        Column(Modifier.fillMaxWidth()) {
                                            Text(observationDescription(reading), color = colors.ink)
                                            val date = reading.occurred_at
                                            Text(if (readableSensorDate(date)) {
                                                if (Regex("^\\d{4}-\\d{2}-\\d{2}$").matches(date.orEmpty())) date.orEmpty()
                                                else sensorLocalDateTime(date.orEmpty())
                                            } else "No readable date", color = if (readableSensorDate(date)) colors.ink3 else colors.amber)
                                        }
                                    }
                                    val shown = pages[sourceType] ?: PAGE_SIZE
                                    if (shown < readings.size) TextButton(onClick = { pages[sourceType] = shown + PAGE_SIZE }) {
                                        Text("Show more $sourceType readings (${readings.size - shown} remaining)")
                                    }
                                    ThemeLinkPicker(sourceType, if (current.status == "pending") links[sourceType] else current.theme_links[sourceType],
                                        known, enabled = current.status == "pending" && action == null && themes is Loadable.Ready,
                                        onChange = { model.setLink(sourceType, it) }, valid = knownIds)
                                    if (themes is Loadable.Ready && known.isEmpty()) Text(
                                        "No themes yet. These readings can still be kept unlinked.", color = colors.ink3)
                                }
                                }
                            }
                        }
                        if (stale) item { Text("New readings arrived while you were reviewing. Check them, then confirm again.", color = colors.amber) }
                        if (error != null) item { SensorNotice(error.orEmpty(), colors.rose) }
                        item {
                            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                HorizontalDivider(color = colors.lineSoft)
                                if (current.status == "pending") {
                                    Button(onClick = { model.confirm(id) }, modifier = Modifier.fillMaxWidth(),
                                        enabled = action == null && themes is Loadable.Ready) {
                                        Text(if (action == "confirm") "Confirming…" else "Confirm & link selected themes")
                                    }
                                    OutlinedButton(onClick = { model.reject(id) }, modifier = Modifier.fillMaxWidth(), enabled = action == null) {
                                        Text(if (action == "reject") "Rejecting…" else "Reject data")
                                    }
                                }
                                TextButton(onClick = { model.delete(id, onBack) }, modifier = Modifier.fillMaxWidth(), enabled = action == null) {
                                    Text(if (action == "delete") "Deleting…" else "Delete batch", color = colors.rose)
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
private fun SensorNotice(text: String, tint: Color) {
    androidx.compose.material3.Surface(border = BorderStroke(1.dp, tint), shape = androidx.compose.material3.MaterialTheme.shapes.small,
        color = LocalIrisColors.current.bg0) { Text(text, color = tint, modifier = Modifier.padding(12.dp)) }
}

@Composable
private fun ThemeLinkPicker(type: String, selected: Long?, themes: List<KnownFact>, enabled: Boolean,
    onChange: (Long?) -> Unit, valid: Set<Long>) {
    var expanded by remember { mutableStateOf(false) }
    val label = "Link $type to an existing theme"
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, color = LocalIrisColors.current.ink2)
        ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { if (enabled) expanded = it }) {
            OutlinedTextField(
                value = themes.firstOrNull { selected != null && selected in valid && it.id.toLongOrNull() == selected }?.fact
                    ?: "Do not link — keep raw reading, not evidence",
                onValueChange = {}, readOnly = true, enabled = enabled, label = { Text(label) },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                modifier = Modifier.fillMaxWidth().menuAnchor(),
            )
            ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                DropdownMenuItem(text = { Text("Do not link — keep raw reading, not evidence") }, onClick = {
                    onChange(null); expanded = false
                })
                themes.forEach { theme -> DropdownMenuItem(text = { Text(theme.fact) }, onClick = {
                    onChange(theme.id.toLongOrNull()); expanded = false
                }) }
            }
        }
    }
}
