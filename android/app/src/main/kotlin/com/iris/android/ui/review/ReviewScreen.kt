package com.iris.android.ui.review

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.IrisLink
import com.iris.android.api.ReviewDay
import com.iris.android.api.ReviewMetrics
import com.iris.android.api.ReviewWeek
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisOrb
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Mono
import com.iris.android.ui.theme.Serif
import java.util.Locale
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ReviewViewModel : ViewModel() {
    private val _week = MutableStateFlow<Loadable<ReviewWeek>>(Loadable.Loading)
    val week = _week.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private var request: Job? = null

    fun refresh() {
        if (request?.isActive == true) return
        request = viewModelScope.launch {
            _refreshing.value = true
            try {
                _week.value = Loadable.Ready(IrisLink.api().send("GET", "/review/latest", null, ReviewWeek.serializer()))
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                _week.value = Loadable.Failed(error.message ?: "Iris couldn't reach your data just now.")
            } finally {
                _refreshing.value = false
            }
        }
    }
}

@Composable
fun ReviewScreen() {
    val model: ReviewViewModel = viewModel()
    val week by model.week.collectAsState()
    val refreshing by model.refreshing.collectAsState()
    LaunchedEffect(Unit) { model.refresh() }
    val data = (week as? Loadable.Ready<ReviewWeek>)?.value

    IrisScaffold(title = "Your week", kicker = data?.let { "your week · ${it.weekStart} — ${it.weekEnd}" }) { padding ->
        when (val current = week) {
            Loadable.Loading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.TopCenter) {
                LoadingState("Iris is composing your week…")
            }
            is Loadable.Failed -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.TopCenter) {
                ErrorState(onRetry = model::refresh)
            }
            is Loadable.Ready -> RefreshableList(refreshing = refreshing, onRefresh = model::refresh) {
                WeeklyContent(current.value, Modifier.fillMaxSize().padding(padding))
            }
        }
    }
}

@Composable
private fun WeeklyContent(week: ReviewWeek, modifier: Modifier = Modifier) {
    val colors = LocalIrisColors.current
    LazyColumn(modifier) {
        item {
            Column(
                Modifier.fillMaxWidth().drawBehind {
                    drawRect(Brush.radialGradient(
                        colors = listOf(colors.sage.copy(alpha = .04f), Color.Transparent),
                        center = Offset(size.width / 2f, 0f), radius = size.width.coerceAtLeast(size.height),
                    ))
                }.padding(horizontal = 20.dp).padding(top = 48.dp, bottom = 40.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                IrisOrb()
                Spacer(Modifier.height(28.dp))
                Kicker("iris's letter")
                Spacer(Modifier.height(18.dp))
                week.letter.split("\n\n").forEachIndexed { index, paragraph ->
                    if (index > 0) Spacer(Modifier.height(16.dp))
                    Text(
                        paragraph, modifier = Modifier.fillMaxWidth(), fontFamily = Serif,
                        fontSize = if (index == 0) 32.sp else 20.sp,
                        lineHeight = if (index == 0) 36.sp else 30.sp,
                        fontStyle = if (index == 0) FontStyle.Normal else FontStyle.Italic,
                        color = if (index == 0) colors.ink else colors.ink2,
                    )
                }
                Spacer(Modifier.height(48.dp))
                DashedDivider()
                Spacer(Modifier.height(32.dp))
                Metrics(week.metrics)
            }
        }
        item {
            HorizontalDivider(color = colors.lineSoft)
            Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 36.dp),
                horizontalAlignment = Alignment.CenterHorizontally) {
                Kicker("· your energy, day by day ·")
                Spacer(Modifier.height(24.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    week.days.forEach { day -> DayBubble(day, Modifier.weight(1f)) }
                }
            }
        }
        item {
            HorizontalDivider(color = colors.lineSoft)
            Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 32.dp)) {
                Kicker("three themes")
                Spacer(Modifier.height(8.dp))
                week.themes.forEachIndexed { index, theme ->
                    Row(Modifier.fillMaxWidth().padding(bottom = 6.dp)) {
                        Text("${index + 1}.", fontFamily = Serif, fontStyle = FontStyle.Italic,
                            fontSize = 18.sp, lineHeight = 26.sp, color = if (index == 0) colors.ink else colors.ink2)
                        Spacer(Modifier.width(8.dp))
                        Text(theme, fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = 18.sp,
                            lineHeight = 26.sp, color = if (index == 0) colors.ink else colors.ink2)
                    }
                }
                Spacer(Modifier.height(24.dp))
                DashedDivider()
                Spacer(Modifier.height(24.dp))
                Kicker("looking ahead")
                Spacer(Modifier.height(8.dp))
                week.lookahead.forEach { entry ->
                    Row(Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                        Text(entry.`when`.uppercase(), Modifier.width(80.dp), fontFamily = Mono,
                            fontSize = 10.sp, letterSpacing = .6.sp, color = colors.ink3)
                        Text(entry.what, fontSize = 12.sp, color = colors.ink,
                            modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

@Composable
private fun Metrics(metrics: ReviewMetrics) {
    val colors = LocalIrisColors.current
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(metrics.energyAvg?.let { String.format(Locale.US, "%.1f", it) } ?: "—",
                fontFamily = Serif, fontSize = 40.sp, color = colors.sage)
            Kicker(metrics.energyAvg?.let { "energy you reported · ${signed(metrics.energyDelta)}" }
                ?: "no energy reported")
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("${metrics.habitsHit}/${metrics.habitsTotal}", fontFamily = Serif, fontSize = 40.sp,
                color = colors.ink)
            Kicker("habits kept")
        }
    }
}

private fun signed(value: Double?): String = when {
    value == null -> "no comparison"
    value == 0.0 -> "0"
    value > 0 -> "+${value.toString().removeSuffix(".0")}" 
    else -> value.toString().removeSuffix(".0")
}

@Composable
private fun DayBubble(day: ReviewDay, modifier: Modifier = Modifier) {
    val colors = LocalIrisColors.current
    val intensity = (day.energy ?: 0) / 10f
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(day.shortName.uppercase(), fontFamily = Mono, fontSize = 10.sp,
            letterSpacing = 1.sp, color = colors.ink4, textAlign = TextAlign.Center)
        Box(Modifier.size(32.dp), contentAlignment = Alignment.BottomCenter) {
            Canvas(Modifier.size((8 + intensity * 24).dp)) {
                drawCircle(
                    brush = Brush.radialGradient(
                        colorStops = arrayOf(
                            0f to Color(0xFFD8EFD2), .55f to Color(0xFFA9C8A3), 1f to Color(0xFF6F8C6A),
                        ),
                        center = Offset(size.width * .35f, size.height * .3f), radius = size.width * .72f,
                    ),
                    alpha = .5f + intensity * .5f,
                )
            }
        }
        Text(day.word, fontFamily = Serif, fontSize = 16.sp, fontStyle = FontStyle.Italic,
            color = colors.ink, textAlign = TextAlign.Center, lineHeight = 19.sp)
    }
}

@Composable
private fun DashedDivider() {
    val color = LocalIrisColors.current.line
    Canvas(Modifier.fillMaxWidth().height(1.dp)) {
        drawLine(color, Offset.Zero, Offset(size.width, 0f), strokeWidth = 1.dp.toPx(),
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 6.dp.toPx())))
    }
}
