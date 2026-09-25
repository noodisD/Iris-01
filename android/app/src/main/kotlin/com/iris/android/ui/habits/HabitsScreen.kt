@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class, androidx.compose.ui.text.ExperimentalTextApi::class)
package com.iris.android.ui.habits

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.R
import com.iris.android.api.Habit
import com.iris.android.api.HabitsTodayResponse
import com.iris.android.api.IrisLink
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisOrb
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.theme.IrisPalette
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Mono
import com.iris.android.ui.theme.Serif
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
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

class HabitsViewModel : ViewModel() {
    private val _habits = MutableStateFlow<Loadable<HabitsTodayResponse>>(Loadable.Loading)
    val habits = _habits.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private val _toggleError = MutableStateFlow(false)
    val toggleError = _toggleError.asStateFlow()
    private val _createError = MutableStateFlow(false)
    val createError = _createError.asStateFlow()
    private val _creating = MutableStateFlow(false)
    val creating = _creating.asStateFlow()
    private val _created = MutableStateFlow(false)
    val created = _created.asStateFlow()
    private val toggleMutex = Mutex()
    private var requestVersion = 0

    fun refresh() { viewModelScope.launch { fetch() } }

    private suspend fun fetch() {
        val version = ++requestVersion
        _refreshing.value = true
        try {
            val response = IrisLink.api().send("GET", "/habits/today", null, HabitsTodayResponse.serializer())
            if (version == requestVersion) _habits.value = Loadable.Ready(response)
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) {
            if (version == requestVersion && _habits.value !is Loadable.Ready) {
                _habits.value = Loadable.Failed(e.message ?: "Habits didn't load.")
            }
        } finally {
            if (version == requestVersion) _refreshing.value = false
        }
    }

    fun toggle(id: String, done: Boolean) {
        viewModelScope.launch {
            toggleMutex.withLock {
                val previous = (_habits.value as? Loadable.Ready)?.value ?: return@withLock
                val original = previous.habits.firstOrNull { it.id == id } ?: return@withLock
                if (original.doneToday == done) return@withLock
                // Cancel the authority of any earlier in-flight GET before the optimistic write.
                ++requestVersion
                _refreshing.value = false
                _toggleError.value = false
                _habits.value = Loadable.Ready(previous.copy(
                    habits = previous.habits.map { habit ->
                        if (habit.id == id) habit.copy(doneToday = done,
                            streakDays = if (done) habit.streakDays + 1 else max(0, habit.streakDays - 1)) else habit
                    },
                    doneCount = previous.habits.count { if (it.id == id) done else it.doneToday },
                ))
                try {
                    val server = IrisLink.api().send("POST", "/habits/$id/toggle",
                        buildJsonObject { put("done", done) }.toString(), Habit.serializer())
                    val current = (_habits.value as? Loadable.Ready)?.value
                    if (current != null) _habits.value = Loadable.Ready(current.copy(
                        habits = current.habits.map { if (it.id == server.id) server else it },
                        doneCount = current.habits.count { if (it.id == server.id) server.doneToday else it.doneToday },
                    ))
                } catch (e: CancellationException) { throw e }
                catch (_: Exception) {
                    _habits.value = Loadable.Ready(previous)
                    _toggleError.value = true
                } finally {
                    fetch()
                }
            }
        }
    }

    fun create(name: String, tag: String) {
        val trimmed = name.trim()
        if (trimmed.isBlank() || _creating.value) return
        viewModelScope.launch {
            _creating.value = true
            _createError.value = false
            _created.value = false
            try {
                IrisLink.api().send("POST", "/habits", buildJsonObject {
                    put("name", trimmed)
                    if (tag.trim().isNotEmpty()) put("tag", tag.trim())
                }.toString(), Habit.serializer())
                _created.value = true
                fetch()
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { _createError.value = true }
            finally { _creating.value = false }
        }
    }

    fun clearCreated() { _created.value = false }
}

@Composable
fun HabitsScreen() {
    val vm: HabitsViewModel = viewModel()
    val result by vm.habits.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val toggleError by vm.toggleError.collectAsState()
    val createError by vm.createError.collectAsState()
    val creating by vm.creating.collectAsState()
    val created by vm.created.collectAsState()
    val colors = LocalIrisColors.current
    var view by remember { mutableStateOf("list") }
    var sheetOpen by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var tag by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { vm.refresh() }
    LaunchedEffect(created) {
        if (created) { sheetOpen = false; name = ""; tag = ""; vm.clearCreated() }
    }
    val response = (result as? Loadable.Ready)?.value
    val title = buildAnnotatedString {
        append("${response?.doneCount ?: 0}")
        withStyle(SpanStyle(color = colors.ink3, fontStyle = FontStyle.Italic)) { append("/${response?.totalCount ?: 0}") }
        append(" today.")
    }
    IrisScaffold(title = title, kicker = "habits · daily practice",
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = { sheetOpen = true }, icon = {
                Icon(painterResource(R.drawable.ic_add), contentDescription = null)
            }, text = { Text("add habit") })
        }) { padding ->
        RefreshableList(refreshing, vm::refresh) {
            LazyColumn(
                Modifier.fillMaxSize().padding(padding),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 96.dp),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                when (val data = result) {
                    Loadable.Loading -> item { LoadingState("Iris is counting your streaks…") }
                    is Loadable.Failed -> item { ErrorState(onRetry = vm::refresh) }
                    is Loadable.Ready -> {
                        val today = data.value
                        item {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text("${today.longestActiveStreak}", fontFamily = Serif, fontSize = 28.sp, color = colors.sage)
                                    Kicker("longest active")
                                }
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text("${(today.consistency30d * 100).roundToInt()}%", fontFamily = Serif, fontSize = 28.sp, color = colors.ink)
                                    Kicker("30d consistency")
                                }
                            }
                        }
                        item {
                            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                                listOf("list", "constellation").forEachIndexed { index, option ->
                                    SegmentedButton(selected = view == option, onClick = { view = option },
                                        shape = SegmentedButtonDefaults.itemShape(index, 2)) { Text(option) }
                                }
                            }
                        }
                        today.suggestion?.let { suggestion -> item {
                            Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.Top) {
                                IrisOrb(14.dp)
                                Text("\"${suggestion.text}\"", fontFamily = Serif, fontStyle = FontStyle.Italic,
                                    fontSize = 20.sp, lineHeight = 28.sp, color = colors.ink)
                            }
                        } }
                        if (toggleError) item {
                            Text("That tick didn't save. Nothing is lost — try again.", fontSize = 13.sp, color = colors.ink3)
                        }
                        if (today.habits.isEmpty()) item {
                            Text("No habits yet. Name one above and tick it off here each day.",
                                fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = 20.sp, color = colors.ink3)
                        } else if (view == "list") {
                            items(today.habits, key = { it.id }) { habit ->
                                IrisCard(Modifier.fillMaxWidth()) { HabitRow(habit) { vm.toggle(habit.id, !habit.doneToday) } }
                            }
                        } else item {
                            Kicker("your habits · sized by current streak")
                            Constellation(today.habits) { habit -> vm.toggle(habit.id, !habit.doneToday) }
                        }
                    }
                }
            }
        }
    }
    if (sheetOpen) ModalBottomSheet(onDismissRequest = { if (!creating) sheetOpen = false }) {
        Column(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            OutlinedTextField(name, { name = it }, label = { Text("A new habit") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(tag, { tag = it }, label = { Text("tag (optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Button(onClick = { vm.create(name, tag) }, enabled = name.isNotBlank() && !creating, modifier = Modifier.fillMaxWidth()) {
                Text("+ add habit")
            }
            if (createError) Text("It wasn't saved. Try again.", fontSize = 12.sp, color = colors.rose)
        }
    }
}

@Composable
private fun HabitRow(habit: Habit, onToggle: () -> Unit) {
    val colors = LocalIrisColors.current
    val accent = habitColor(habit.color)
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(40.dp).semantics {
                contentDescription = "Mark ${habit.name} ${if (habit.doneToday) "not done" else "done"}"
            }.clickable(onClick = onToggle), contentAlignment = Alignment.Center) {
                Box(Modifier.size(24.dp).background(if (habit.doneToday) accent else Color.Transparent, CircleShape)
                    .border(BorderStroke(1.5.dp, if (habit.doneToday) accent else colors.line), CircleShape),
                    contentAlignment = Alignment.Center) {
                    if (habit.doneToday) Text("✓", color = Color(0xFF14140F), fontSize = 12.sp)
                }
            }
            Text(habit.name, Modifier.weight(1f), fontFamily = Serif, fontSize = 22.sp, color = colors.ink)
            Text("${habit.streakDays}", fontFamily = Serif, fontSize = 40.sp,
                color = if (habit.streakDays == 0) colors.ink3 else accent)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(habit.tag, style = IrisType.mono, color = colors.ink3)
                habit.intent?.let { Text("↳ $it", fontStyle = FontStyle.Italic, fontSize = 12.sp, color = colors.ink2) }
            }
            Column(horizontalAlignment = Alignment.End) {
                Kicker("day streak")
                Text("best ${habit.bestStreak}", style = IrisType.mono, color = colors.ink4)
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            habit.recentDays.forEachIndexed { index, done ->
                Spacer(Modifier.size(8.dp).alpha(if (done != 0) max(0.45f, 1f - (habit.recentDays.size - index) / 120f) else 1f)
                    .background(if (done != 0) accent else colors.line, CircleShape))
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("${habit.recentDays.size} days ago".uppercase(), fontFamily = Mono, fontSize = 9.sp, color = colors.ink4)
            Text("TODAY", fontFamily = Mono, fontSize = 9.sp, color = colors.ink4)
        }
    }
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
