@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class, androidx.compose.ui.text.ExperimentalTextApi::class)
package com.iris.android.ui.habits

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.R
import com.iris.android.api.Habit
import com.iris.android.api.HabitDay
import com.iris.android.api.HabitDayResult
import com.iris.android.api.IrisLink
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ConfirmDialog
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.theme.IrisPalette
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Mono
import com.iris.android.ui.theme.Serif
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Resolve exactly the seven web palette tokens or a six-digit CSS hex value. */
fun habitColor(name: String): Color = when (name) {
    "sage" -> IrisPalette.sage
    "amber" -> IrisPalette.amber
    "indigo" -> IrisPalette.indigo
    "rose" -> IrisPalette.rose
    "ink" -> IrisPalette.ink
    "ink-2" -> IrisPalette.ink2
    "ink-3" -> IrisPalette.ink3
    else -> if (name.length == 7 && name[0] == '#' && name.drop(1).all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) {
        Color(0xFF000000L or name.substring(1).toLong(16))
    } else IrisPalette.sage
}


private val PERIODS = listOf("daily" to "Daily", "weekly" to "Weekly", "monthly" to "Monthly")

/**
 * Habits on the phone, as on the web (ADR-0034): daily, weekly and monthly tabs,
 * any recent day marked with a double-tap or given a note with a tap, habits
 * edited, archived, deleted and put in order.
 */
class HabitsViewModel : ViewModel() {
    private val _habits = MutableStateFlow<Loadable<List<Habit>>>(Loadable.Loading)
    val habits = _habits.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error = _error.asStateFlow()
    private val _busy = MutableStateFlow(false)
    val busy = _busy.asStateFlow()
    private var requestVersion = 0

    fun refresh() { viewModelScope.launch { fetch() } }

    private suspend fun fetch() {
        val version = ++requestVersion
        _refreshing.value = true
        try {
            val list = IrisLink.api().send("GET", "/habits", null, ListSerializer(Habit.serializer()))
            if (version == requestVersion) _habits.value = Loadable.Ready(list)
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) {
            if (version == requestVersion && _habits.value !is Loadable.Ready) {
                _habits.value = Loadable.Failed(e.message ?: "Habits didn't load.")
            }
        } finally {
            if (version == requestVersion) _refreshing.value = false
        }
    }

    /** Run one change, show what went wrong in words, and reload from the server. */
    private fun change(what: String, onDone: () -> Unit = {}, block: suspend () -> Unit) {
        viewModelScope.launch {
            _busy.value = true
            _error.value = null
            try { block(); onDone() }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                com.iris.android.telemetry.Telemetry.error("HabitsScreen.$what", e)
                _error.value = "That didn't save. Nothing is lost; try again."
            } finally {
                _busy.value = false
                fetch()
            }
        }
    }

    /** Mark a day done or not done; the day's note is kept. */
    fun toggleDay(id: String, date: LocalDate, done: Boolean) {
        val previous = (_habits.value as? Loadable.Ready)?.value
        if (previous != null) {
            _habits.value = Loadable.Ready(previous.map { h ->
                if (h.id != id) h else {
                    val dots = h.recentStart?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
                    val index = dots?.let { java.time.temporal.ChronoUnit.DAYS.between(it, date).toInt() } ?: -1
                    h.copy(doneToday = if (date == LocalDate.now()) done else h.doneToday,
                        recentStatus = if (index in h.recentStatus.indices)
                            h.recentStatus.toMutableList().apply { this[index] = if (done) "done" else "none" } else h.recentStatus)
                }
            })
        }
        change("toggleDay") {
            IrisLink.api().send("POST", "/habits/$id/toggle", buildJsonObject {
                put("done", done); put("date", date.toString())
            }.toString(), Habit.serializer())
        }
    }

    suspend fun loadDay(id: String, date: LocalDate): HabitDay? =
        IrisLink.api().send("GET", "/habits/$id/days?start=$date&end=$date", null,
            ListSerializer(HabitDay.serializer())).firstOrNull()

    fun saveDay(id: String, date: LocalDate, status: String, note: String, onDone: () -> Unit) =
        change("saveDay", onDone) {
            IrisLink.api().send("PUT", "/habits/$id/days/$date", buildJsonObject {
                put("status", status)
                put("note", note.trim().ifEmpty { null }?.let { JsonPrimitive(it) } ?: JsonNull)
            }.toString(), HabitDayResult.serializer())
        }

    fun create(name: String, tag: String, frequency: String, target: Int, onDone: () -> Unit) {
        if (name.isBlank()) return
        change("create", onDone) {
            IrisLink.api().send("POST", "/habits", buildJsonObject {
                put("name", name.trim())
                if (tag.isNotBlank()) put("tag", tag.trim())
                put("frequency", frequency)
                put("target", if (frequency == "daily") 1 else target)
            }.toString(), Habit.serializer())
        }
    }

    fun update(id: String, fields: JsonObject, onDone: () -> Unit) = change("update", onDone) {
        IrisLink.api().send("PATCH", "/habits/$id", fields.toString(), Habit.serializer())
    }

    fun delete(id: String, onDone: () -> Unit) = change("delete", onDone) {
        IrisLink.api().send("DELETE", "/habits/$id", null, JsonObject.serializer())
    }

    /** Move a habit one place within its tab; the list moves at once. */
    fun move(tabIds: List<String>, id: String, delta: Int) {
        val ids = movedIds(tabIds, id, delta) ?: return
        val previous = (_habits.value as? Loadable.Ready)?.value
        if (previous != null) {
            val byId = previous.associateBy { it.id }
            val queue = ArrayDeque(ids.mapNotNull { byId[it] })
            _habits.value = Loadable.Ready(previous.map { if (it.id in ids) queue.removeFirst() else it })
        }
        change("move") {
            IrisLink.api().send("PUT", "/habits/order",
                buildJsonObject { put("ids", JsonArray(ids.map { JsonPrimitive(it) })) }.toString(), JsonObject.serializer())
        }
    }
}

private val DAY_LABEL: DateTimeFormatter = DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.getDefault())
private val SHORT_LABEL: DateTimeFormatter = DateTimeFormatter.ofPattern("d MMM", Locale.getDefault())

@Composable
fun HabitsScreen() {
    val vm: HabitsViewModel = viewModel()
    val result by vm.habits.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val error by vm.error.collectAsState()
    val busy by vm.busy.collectAsState()
    val colors = LocalIrisColors.current
    var tab by remember { mutableStateOf("daily") }
    var view by remember { mutableStateOf("list") }
    var adding by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<Habit?>(null) }
    var noteFor by remember { mutableStateOf<Pair<Habit, LocalDate>?>(null) }
    LaunchedEffect(Unit) { vm.refresh() }

    val all = (result as? Loadable.Ready)?.value.orEmpty()
    val active = all.filter { !it.archived }
    val shown = active.filter { frequencyOf(it) == tab }
    val onTarget = shown.count { if (tab == "daily") it.doneToday else it.periodMet }
    val title = buildAnnotatedString {
        append("$onTarget")
        withStyle(SpanStyle(color = colors.ink3, fontStyle = FontStyle.Italic)) { append("/${shown.size}") }
        append(if (tab == "daily") " today." else if (tab == "weekly") " this week." else " this month.")
    }
    IrisScaffold(title = title, kicker = "habits",
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = { adding = true }, icon = {
                Icon(painterResource(R.drawable.ic_add), contentDescription = null)
            }, text = { Text("add habit") })
        }) { padding ->
        RefreshableList(refreshing, vm::refresh) {
            LazyColumn(
                Modifier.fillMaxSize().padding(padding),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 20.dp, end = 20.dp, top = 16.dp, bottom = 96.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                when (result) {
                    Loadable.Loading -> item { LoadingState("Iris is counting your streaks…") }
                    is Loadable.Failed -> item { ErrorState(onRetry = vm::refresh) }
                    is Loadable.Ready -> {
                        item {
                            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                                PERIODS.forEachIndexed { index, (value, label) ->
                                    SegmentedButton(selected = tab == value, onClick = { tab = value },
                                        shape = SegmentedButtonDefaults.itemShape(index, PERIODS.size)) {
                                        Text("$label ${active.count { frequencyOf(it) == value }}")
                                    }
                                }
                            }
                        }
                        item {
                            Text("Double-tap a day to mark it done; tap it for that day's note. Tap a habit's name to edit it.",
                                fontSize = 13.sp, color = colors.ink3)
                        }
                        if (tab == "daily" && shown.size > 1) item {
                            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                                listOf("list", "constellation").forEachIndexed { index, option ->
                                    SegmentedButton(selected = view == option, onClick = { view = option },
                                        shape = SegmentedButtonDefaults.itemShape(index, 2)) { Text(option) }
                                }
                            }
                        }
                        error?.let { message -> item { Text(message, fontSize = 13.sp, color = colors.rose) } }
                        if (shown.isEmpty()) item {
                            Text(if (tab == "daily") "No daily habits yet. Add one and tick it off here each day."
                                else "No ${tab} habits yet. Add one and say how many times a ${if (tab == "weekly") "week" else "month"}.",
                                fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = 20.sp, color = colors.ink3)
                        } else if (tab == "daily" && view == "constellation") item {
                            Kicker("your daily habits · sized by current streak")
                            Constellation(shown) { habit -> vm.toggleDay(habit.id, LocalDate.now(), !habit.doneToday) }
                        } else {
                            val ids = shown.map { it.id }
                            items(shown, key = { it.id }) { habit ->
                                IrisCard(Modifier.fillMaxWidth()) {
                                    HabitRow(habit,
                                        canUp = ids.first() != habit.id, canDown = ids.last() != habit.id,
                                        onMove = { delta -> vm.move(ids, habit.id, delta) },
                                        onToggleToday = { vm.toggleDay(habit.id, LocalDate.now(), !habit.doneToday) },
                                        onDoubleTapDay = { dot -> vm.toggleDay(habit.id, dot.date, dot.status != "done") },
                                        onTapDay = { dot -> noteFor = habit to dot.date },
                                        onEdit = { editing = habit })
                                }
                            }
                        }
                        val archived = all.filter { it.archived }
                        if (archived.isNotEmpty()) {
                            item { Kicker("archived · tap to restore or delete") }
                            items(archived, key = { "archived-${it.id}" }) { habit ->
                                Text(habit.name, Modifier.fillMaxWidth().clickable { editing = habit }.padding(vertical = 6.dp),
                                    fontSize = 15.sp, color = colors.ink2)
                            }
                        }
                    }
                }
            }
        }
    }
    if (adding) AddHabitSheet(defaultFrequency = tab, busy = busy, onDismiss = { adding = false }) { name, tag, frequency, target ->
        vm.create(name, tag, frequency, target) { adding = false; tab = frequency }
    }
    editing?.let { habit -> EditHabitSheet(habit, busy, onDismiss = { editing = null },
        onSave = { fields -> vm.update(habit.id, fields) { editing = null } },
        onDelete = { vm.delete(habit.id) { editing = null } }) }
    noteFor?.let { (habit, date) -> NoteSheet(vm, habit, date, busy, onDismiss = { noteFor = null }) }
}

@Composable
private fun HabitRow(
    habit: Habit, canUp: Boolean, canDown: Boolean, onMove: (Int) -> Unit, onToggleToday: () -> Unit,
    onDoubleTapDay: (DayDot) -> Unit, onTapDay: (DayDot) -> Unit, onEdit: () -> Unit,
) {
    val colors = LocalIrisColors.current
    val accent = habitColor(habit.color)
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("▲", Modifier.size(28.dp, 20.dp).clickable(enabled = canUp) { onMove(-1) }
                    .semantics { contentDescription = "Move ${habit.name} up" },
                    fontSize = 11.sp, color = if (canUp) colors.ink3 else colors.line, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                Text("▼", Modifier.size(28.dp, 20.dp).clickable(enabled = canDown) { onMove(1) }
                    .semantics { contentDescription = "Move ${habit.name} down" },
                    fontSize = 11.sp, color = if (canDown) colors.ink3 else colors.line, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            }
            Box(Modifier.size(40.dp).semantics {
                contentDescription = "Mark ${habit.name} ${if (habit.doneToday) "not done" else "done"} today"
            }.clickable(onClick = onToggleToday), contentAlignment = Alignment.Center) {
                Box(Modifier.size(24.dp).background(if (habit.doneToday) accent else Color.Transparent, CircleShape)
                    .border(BorderStroke(1.5.dp, if (habit.doneToday) accent else colors.line), CircleShape),
                    contentAlignment = Alignment.Center) {
                    if (habit.doneToday) Text("✓", color = Color(0xFF14140F), fontSize = 12.sp)
                }
            }
            Text(habit.name, Modifier.weight(1f).clickable(onClick = onEdit), fontFamily = Serif, fontSize = 21.sp, color = colors.ink)
            Column(horizontalAlignment = Alignment.End) {
                Text("${habit.streakDays}", fontFamily = Serif, fontSize = 34.sp,
                    color = if (habit.streakDays == 0) colors.ink3 else accent)
                Text("${habit.streakUnit} streak · best ${habit.bestStreak}", style = IrisType.mono, color = colors.ink4)
            }
        }
        if (habit.tag.isNotBlank() || habit.intent != null || periodProgress(habit) != null) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                if (habit.tag.isNotBlank()) Text(habit.tag, style = IrisType.mono, color = colors.ink3)
                habit.intent?.let { Text("↳ $it", fontStyle = FontStyle.Italic, fontSize = 12.sp, color = colors.ink2) }
                periodProgress(habit)?.let { Text(it, fontSize = 13.sp, color = if (habit.periodMet) colors.sage else colors.ink3) }
            }
        }
        val dots = recentDots(habit)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            dots.forEach { dot ->
                val label = "${dot.date.format(SHORT_LABEL)}: ${when (dot.status) { "done" -> "done"; "skipped" -> "skipped"; else -> "not done" }}" +
                    if (dot.noted) ", with a note" else ""
                Box(Modifier.size(18.dp)
                    .semantics { contentDescription = label; onClick(label = "open the note") { onTapDay(dot); true } }
                    .pointerInput(dot) { detectTapGestures(onTap = { onTapDay(dot) }, onDoubleTap = { onDoubleTapDay(dot) }) },
                    contentAlignment = Alignment.Center) {
                    Box(Modifier.size(16.dp)
                        .background(if (dot.status == "done") accent else if (dot.status == "skipped") Color.Transparent else colors.line, CircleShape)
                        .then(if (dot.status == "skipped") Modifier.border(BorderStroke(1.5.dp, accent), CircleShape) else Modifier))
                    if (dot.noted) Box(Modifier.align(Alignment.BottomCenter).size(4.dp).background(IrisPalette.amber, CircleShape))
                }
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("${dots.size} days ago".uppercase(), fontFamily = Mono, fontSize = 9.sp, color = colors.ink4)
            Text("TODAY", fontFamily = Mono, fontSize = 9.sp, color = colors.ink4)
        }
    }
}

/** A day's note. Double-tapping the day marks it done; skipping is here because the phone has no calendar. */
@Composable
private fun NoteSheet(vm: HabitsViewModel, habit: Habit, date: LocalDate, busy: Boolean, onDismiss: () -> Unit) {
    val colors = LocalIrisColors.current
    var loaded by remember(habit.id, date) { mutableStateOf<HabitDay?>(null) }
    var ready by remember(habit.id, date) { mutableStateOf(false) }
    var note by remember(habit.id, date) { mutableStateOf("") }
    LaunchedEffect(habit.id, date) {
        loaded = runCatching { vm.loadDay(habit.id, date) }.getOrNull()
        note = loaded?.note.orEmpty()
        ready = true
    }
    val status = loaded?.status ?: "none"
    ModalBottomSheet(onDismissRequest = { if (!busy) onDismiss() }) {
        Column(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(date.format(DAY_LABEL), fontFamily = Serif, fontSize = 22.sp, color = colors.ink)
            Text("${habit.name} · ${when (status) { "done" -> "done"; "skipped" -> "skipped"; else -> "not done" }}. Double-tap the day to change that.",
                fontSize = 13.sp, color = colors.ink3)
            OutlinedTextField(note, { note = it }, label = { Text("Note for this day") }, enabled = ready,
                placeholder = { Text("How it went") }, minLines = 6,
                modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp))
            Button(onClick = { vm.saveDay(habit.id, date, status, note, onDismiss) }, enabled = ready && !busy,
                modifier = Modifier.fillMaxWidth()) { Text("Save note") }
            TextButton(onClick = { vm.saveDay(habit.id, date, if (status == "skipped") "none" else "skipped", note, onDismiss) },
                enabled = ready && !busy) {
                Text(if (status == "skipped") "Not skipped after all" else "Mark as skipped (a rest day)")
            }
        }
    }
}

@Composable
private fun FrequencyPicker(value: String, onChange: (String) -> Unit) {
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        PERIODS.forEachIndexed { index, (option, label) ->
            SegmentedButton(selected = value == option, onClick = { onChange(option) },
                shape = SegmentedButtonDefaults.itemShape(index, PERIODS.size)) { Text(label) }
        }
    }
}

@Composable
private fun TargetField(frequency: String, target: String, onChange: (String) -> Unit) {
    if (frequency == "daily") return
    OutlinedTextField(target, { onChange(it.filter(Char::isDigit).take(2)) },
        label = { Text("Times a ${if (frequency == "weekly") "week" else "month"}") }, singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
}

@Composable
private fun AddHabitSheet(defaultFrequency: String, busy: Boolean, onDismiss: () -> Unit,
                          onAdd: (String, String, String, Int) -> Unit) {
    var name by remember { mutableStateOf("") }
    var tag by remember { mutableStateOf("") }
    var frequency by remember { mutableStateOf(defaultFrequency) }
    var target by remember { mutableStateOf("1") }
    ModalBottomSheet(onDismissRequest = { if (!busy) onDismiss() }) {
        Column(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            OutlinedTextField(name, { name = it }, label = { Text("A new habit") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            FrequencyPicker(frequency) { frequency = it }
            TargetField(frequency, target) { target = it }
            OutlinedTextField(tag, { tag = it }, label = { Text("tag (optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Button(onClick = { onAdd(name, tag, frequency, (target.toIntOrNull() ?: 1).coerceIn(1, 31)) },
                enabled = name.isNotBlank() && !busy, modifier = Modifier.fillMaxWidth()) { Text("+ add habit") }
        }
    }
}

@Composable
private fun EditHabitSheet(habit: Habit, busy: Boolean, onDismiss: () -> Unit,
                           onSave: (JsonObject) -> Unit, onDelete: () -> Unit) {
    val colors = LocalIrisColors.current
    var name by remember(habit.id) { mutableStateOf(habit.name) }
    var intent by remember(habit.id) { mutableStateOf(habit.intent.orEmpty()) }
    var tag by remember(habit.id) { mutableStateOf(habit.tag) }
    var frequency by remember(habit.id) { mutableStateOf(frequencyOf(habit)) }
    var target by remember(habit.id) { mutableStateOf(habit.target.toString()) }
    var confirmDelete by remember { mutableStateOf(false) }
    ModalBottomSheet(onDismissRequest = { if (!busy) onDismiss() }) {
        Column(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            if (habit.archived) Text("Archived: hidden from your lists, history kept.", fontSize = 13.sp, color = colors.amber)
            OutlinedTextField(name, { name = it }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(intent, { intent = it }, label = { Text("What it is for") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(tag, { tag = it }, label = { Text("Tag") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            FrequencyPicker(frequency) { frequency = it }
            TargetField(frequency, target) { target = it }
            Button(onClick = {
                onSave(buildJsonObject {
                    put("name", name.trim())
                    put("intent", intent.trim().ifEmpty { null }?.let { JsonPrimitive(it) } ?: JsonNull)
                    put("tag", tag.trim().ifEmpty { null }?.let { JsonPrimitive(it) } ?: JsonNull)
                    put("frequency", frequency)
                    if (frequency != "daily") put("target", (target.toIntOrNull() ?: 1).coerceIn(1, 31))
                })
            }, enabled = name.isNotBlank() && !busy, modifier = Modifier.fillMaxWidth()) { Text("Save changes") }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(onClick = { onSave(buildJsonObject { put("archived", !habit.archived) }) }, enabled = !busy) {
                    Text(if (habit.archived) "Restore" else "Archive")
                }
                TextButton(onClick = { confirmDelete = true }, enabled = !busy) { Text("Delete…", color = colors.rose) }
            }
        }
    }
    if (confirmDelete) ConfirmDialog(
        text = "Delete ${habit.name} and every day of it? Archive keeps the history.",
        confirmLabel = "Delete for good",
        onConfirm = { confirmDelete = false; onDelete() },
        onDismiss = { confirmDelete = false })
}

private data class RingPosition(val x: Float, val y: Float, val radius: Float)
private fun position(index: Int, count: Int, streakDays: Int): RingPosition {
    val angle = index.toDouble() / count * 2 * PI - PI / 2
    return RingPosition(380f + cos(angle).toFloat() * 200f,
        210f + sin(angle).toFloat() * 150f, 40f + streakDays / 21f * 28f)
}

@Composable
private fun Constellation(habits: List<Habit>, onToggle: (Habit) -> Unit) {
    val colors = LocalIrisColors.current
    val measurer = rememberTextMeasurer()
    val positions = remember(habits) { habits.mapIndexed { index, habit -> position(index, habits.size, habit.streakDays) } }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val scale = maxWidth.value / 760f
        val labels = remember(habits, scale) {
            habits.map { habit ->
                val ink = if (habit.doneToday) Color(0xFF14140F) else colors.ink
                val streakInk = if (habit.doneToday) Color(0xFF14140F) else colors.ink3
                measurer.measure(habit.name.substringBefore(' '), style = TextStyle(fontFamily = Serif,
                    fontStyle = FontStyle.Italic, fontSize = (15f * scale).sp, color = ink)) to
                    measurer.measure("${habit.streakDays}d", style = TextStyle(fontFamily = Mono,
                        fontSize = (10f * scale).sp, color = streakInk))
            }
        }
        Canvas(Modifier.fillMaxWidth().aspectRatio(760f / 420f)
            .pointerInput(habits, positions) {
                detectTapGestures { tap ->
                    val ratio = size.width / 760f
                    for (index in habits.indices.reversed()) {
                        val p = positions[index]
                        val dx = tap.x / ratio - p.x
                        val dy = tap.y / ratio - p.y
                        if (dx * dx + dy * dy <= (p.radius + 8f) * (p.radius + 8f)) {
                            onToggle(habits[index]); break
                        }
                    }
                }
            }) {
            val ratio = size.width / 760f
            habits.forEachIndexed { index, habit ->
                val p = positions[index]
                val center = Offset(p.x * ratio, p.y * ratio)
                val accent = habitColor(habit.color)
                drawCircle(accent.copy(alpha = if (habit.doneToday) 0.4f else 0.1f),
                    radius = (p.radius + 8f) * ratio, center = center, style = Stroke(width = ratio))
                drawCircle(if (habit.doneToday) accent.copy(alpha = 0.92f) else colors.bg2,
                    radius = p.radius * ratio, center = center)
                if (!habit.doneToday) drawCircle(accent, radius = p.radius * ratio, center = center,
                    style = Stroke(width = 1.5f * ratio))
                val (name, streak) = labels[index]
                drawText(name, topLeft = Offset(center.x - name.size.width / 2f,
                    center.y - 2f * ratio - name.size.height / 2f))
                drawText(streak, topLeft = Offset(center.x - streak.size.width / 2f,
                    center.y + 14f * ratio - streak.size.height / 2f))
            }
        }
    }
}
