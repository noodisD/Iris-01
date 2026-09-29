package com.iris.android.ui.patterns

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iris.android.api.DayDifference
import com.iris.android.api.DayDifferenceDetail
import com.iris.android.api.Difference
import com.iris.android.api.DifferenceDetail
import com.iris.android.api.IrisLink
import com.iris.android.api.Occasion
import com.iris.android.api.OutcomePair
import com.iris.android.api.PATTERN_VERDICTS
import com.iris.android.api.coLabelDiscussionRoute
import com.iris.android.api.dayDiscussionRoute
import com.iris.android.api.pairDiscussionRoute
import com.iris.android.api.patternRoute
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.CancellationException

@Composable
private fun SourceAccount(o: Occasion, onNavigate: (String) -> Unit) {
    val colors = LocalIrisColors.current
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Recorded ${o.recordedOn ?: "date unknown"} · provisional ${o.tone}", color = colors.ink3, fontSize = 12.sp)
        Text("${o.response}${o.outcome?.let { " → $it" } ?: ""}", color = colors.ink, fontSize = 14.sp)
        o.explanation?.let { Text("Your interpretation in the entry: “$it”", color = colors.ink3,
            fontStyle = FontStyle.Italic, fontSize = 12.sp) }
        o.citations.forEach { citation ->
            Text("“${citation.text}”", color = colors.ink2, fontStyle = FontStyle.Italic, fontSize = 12.sp)
            if (citation.sourceType == "reflection") TextButton(onClick = {
                onNavigate("journal?entry=${Uri.encode(citation.entryId)}")
            }) { Text("Open entry") }
        }
    }
}

@Composable
internal fun ContrastCard(d: Difference, range: String, onNavigate: (String) -> Unit,
                          enabled: Boolean, error: String?, onJudge: (Difference, String?, String?) -> Unit) {
    val colors = LocalIrisColors.current
    var expanded by rememberSaveable(range, d.patternId, d.otherId) { mutableStateOf(false) }
    var request by rememberSaveable(range, d.patternId, d.otherId) { mutableIntStateOf(0) }
    var detail by remember(range, d.patternId, d.otherId, d.snapshot) {
        mutableStateOf<Loadable<DifferenceDetail>>(Loadable.Loading)
    }
    LaunchedEffect(expanded, range, d.patternId, d.otherId, d.snapshot, request) {
        if (expanded) {
            detail = Loadable.Loading
            try {
                detail = Loadable.Ready(IrisLink.api().send("GET",
                    "/differences/${Uri.encode(d.patternId)}/${Uri.encode(d.otherId)}?range=$range",
                    null, DifferenceDetail.serializer()))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { detail = Loadable.Failed(e.message ?: "Evidence unavailable.") }
        }
    }
    IrisCard(Modifier.fillMaxWidth().alpha(if (d.dismissed) 0.65f else 1f)) {
        Text("${d.otherName} was labelled more often among ${d.patternName} accounts read as " +
            if (d.worseRate > d.betterRate) "worse." else "better.",
            fontFamily = Serif, fontSize = 18.sp, color = colors.ink)
        Text("Read as worse: ${d.worse}/${d.worseTotal} (${(d.worseRate * 100).toInt()}%). " +
            "Read as better: ${d.better}/${d.betterTotal} (${(d.betterRate * 100).toInt()}%).",
            color = colors.ink2, fontSize = 13.sp)
        Text("Exploratory · ${d.coverage.entryCount} entries. Not labelled with ${d.otherName} " +
            "does not mean it was absent.", color = colors.ink3, fontSize = 12.sp)
        TextButton(onClick = { onNavigate(patternRoute(d.patternId, range)) }) { Text(d.patternName) }
        TextButton(onClick = { onNavigate(patternRoute(d.otherId, range)) }) { Text(d.otherName) }
        TextButton(onClick = { onNavigate(coLabelDiscussionRoute(d, range)) }) { Text("Explore with Iris") }
        TextButton(onClick = { expanded = !expanded }) { Text(if (expanded) "Hide evidence" else "See the evidence") }
        if (expanded) when (val loaded = detail) {
            is Loadable.Loading -> LoadingState("Opening contributing accounts…")
            is Loadable.Failed -> ErrorState(loaded.message, onRetry = { request++ })
            is Loadable.Ready -> {
                for (group in listOf("betterWith", "betterWithout", "worseWith", "worseWithout")) {
                    val accounts = loaded.value.groups[group].orEmpty()
                    var shown by rememberSaveable(range, d.patternId, d.otherId, group) { mutableIntStateOf(5) }
                    Kicker("$group · ${accounts.size}")
                    accounts.take(shown).forEach { SourceAccount(it, onNavigate) }
                    if (shown < accounts.size) TextButton(onClick = { shown += 5 }) { Text("Show more") }
                }
                Text("${loaded.value.mixedExcluded} mixed accounts excluded from both denominators.",
                    color = colors.ink3, fontSize = 12.sp)
            }
        }
        FeedbackForm("co/${d.patternId}/${d.otherId}", PATTERN_VERDICTS, d.verdict?.verdict,
            d.verdict?.note, enabled, error) { verdict, note -> onJudge(d, verdict, note) }
    }
}

@Composable
internal fun PairCard(pair: OutcomePair, range: String, onNavigate: (String) -> Unit,
                      enabled: Boolean, error: String?, onJudge: (OutcomePair, String?, String?) -> Unit) {
    val colors = LocalIrisColors.current
    IrisCard(Modifier.fillMaxWidth()) {
        Kicker("two recorded situations to compare · ${pair.patternName}")
        Kicker("read as better")
        SourceAccount(pair.better, onNavigate)
        Kicker("read as worse")
        SourceAccount(pair.worse, onNavigate)
        Text("What do you make of the difference between these situations?",
            fontFamily = Serif, fontSize = 18.sp, color = colors.ink)
        Text("${pair.betterTotal} better · ${pair.worseTotal} worse · ${pair.mixedTotal} mixed. " +
            "The response did not necessarily cause the outcome.", color = colors.ink3, fontSize = 12.sp)
        TextButton(onClick = { onNavigate(patternRoute(pair.patternId, range)) }) { Text("See the evidence") }
        TextButton(onClick = { onNavigate(pairDiscussionRoute(pair, range)) }) { Text("Explore with Iris") }
        FeedbackForm("pair/${pair.patternId}", PATTERN_VERDICTS, pair.verdict?.verdict,
            pair.verdict?.note, enabled, error) { verdict, note -> onJudge(pair, verdict, note) }
    }
}

@Composable
internal fun MeasuredCard(d: DayDifference, range: String, onNavigate: (String) -> Unit,
                          enabled: Boolean, error: String?, onJudge: (DayDifference, String?, String?) -> Unit) {
    val colors = LocalIrisColors.current
    var expanded by rememberSaveable(range, d.outcome, d.split) { mutableStateOf(false) }
    var request by rememberSaveable(range, d.outcome, d.split) { mutableIntStateOf(0) }
    var detail by remember(range, d.outcome, d.split, d.snapshot) {
        mutableStateOf<Loadable<DayDifferenceDetail>>(Loadable.Loading)
    }
    LaunchedEffect(expanded, range, d.outcome, d.split, d.snapshot, request) {
        if (expanded) {
            detail = Loadable.Loading
            try {
                detail = Loadable.Ready(IrisLink.api().send("GET",
                    "/day-differences/${Uri.encode(d.outcome)}/${Uri.encode(d.split)}?range=$range",
                    null, DayDifferenceDetail.serializer()))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { detail = Loadable.Failed(e.message ?: "Day evidence unavailable.") }
        }
    }
    IrisCard(Modifier.fillMaxWidth()) {
        Text("${d.outcome.replace('_', ' ')} — ${d.leftLabel}: ${d.leftMean} across ${d.leftCount} days; " +
            "${d.rightLabel}: ${d.rightMean} across ${d.rightCount} days.",
            fontFamily = Serif, fontSize = 18.sp, color = colors.ink)
        Text("Recorded ${d.coverage.recordedFrom}–${d.coverage.recordedTo}. " +
            "Observational; not a cause or personal rule.", color = colors.ink3, fontSize = 12.sp)
        TextButton(onClick = { expanded = !expanded }) { Text(if (expanded) "Hide days" else "See contributing days") }
        TextButton(onClick = { onNavigate(dayDiscussionRoute(d, range)) }) { Text("Explore with Iris") }
        if (expanded) when (val loaded = detail) {
            is Loadable.Loading -> LoadingState("Opening contributing days…")
            is Loadable.Failed -> ErrorState(loaded.message, onRetry = { request++ })
            is Loadable.Ready -> {
                for ((side, days) in listOf("left" to loaded.value.leftDays, "right" to loaded.value.rightDays)) {
                    var shown by rememberSaveable(range, d.outcome, d.split, side) { mutableIntStateOf(5) }
                    Kicker("${if (side == "left") d.leftLabel else d.rightLabel} · ${days.size}")
                    days.take(shown).forEach { day ->
                        Text("${day.day} · score ${day.value} · measured ${day.splitValue}", color = colors.ink2)
                        day.entryIds.forEach { id ->
                            TextButton(onClick = { onNavigate("journal?entry=${Uri.encode(id)}") }) {
                                Text("Open check-in")
                            }
                        }
                    }
                    if (shown < days.size) TextButton(onClick = { shown += 5 }) { Text("Show more days") }
                }
                Kicker("how calculated")
                Text("Threshold ${d.threshold ?: "office/home"} · permutation p = ${d.pValue}. " +
                    "Five days per group, one-point mean gap and p ≤ .01 required; not causal confidence.",
                    color = colors.ink3, fontSize = 12.sp)
                Text("Excluded: ${loaded.value.excluded.entries.joinToString("; ") { "${it.key}: ${it.value}" }}",
                    color = colors.ink3, fontSize = 12.sp)
            }
        }
        FeedbackForm("day/${d.outcome}/${d.split}", PATTERN_VERDICTS, d.verdict?.verdict,
            d.verdict?.note, enabled, error) { verdict, note -> onJudge(d, verdict, note) }
    }
}
