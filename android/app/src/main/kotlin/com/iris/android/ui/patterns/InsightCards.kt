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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iris.android.api.DayDifference
import com.iris.android.api.DayDifferenceDetail
import com.iris.android.api.InsightDetail
import com.iris.android.api.IrisLink
import com.iris.android.api.PATTERN_VERDICTS
import com.iris.android.api.PersonalInsight
import com.iris.android.api.dayDiscussionRoute
import com.iris.android.api.insightDiscussionRoute
import com.iris.android.api.insightRoute
import com.iris.android.api.patternRoute
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.CancellationException

private fun insightKind(kind: String) = when (kind) {
    "function_and_tradeoff" -> "A possible function and tradeoff"
    "contextual_difference" -> "Different responses in one context"
    "shared_concern" -> "A possible shared concern"
    else -> kind
}

@Composable
internal fun PersonalInsightCard(insight: PersonalInsight, range: String,
    onNavigate: (String) -> Unit, enabled: Boolean, error: String?,
    onJudge: (PersonalInsight, String?, String?) -> Unit, initiallyExpanded: Boolean = false) {
    val colors = LocalIrisColors.current
    var expanded by rememberSaveable(range, insight.id) { mutableStateOf(initiallyExpanded) }
    var request by rememberSaveable(range, insight.id) { mutableIntStateOf(0) }
    var detail by remember(range, insight.id, insight.snapshot) {
        mutableStateOf<Loadable<InsightDetail>>(Loadable.Loading)
    }
    LaunchedEffect(expanded, range, insight.id, insight.snapshot, request) {
        if (expanded) {
            detail = Loadable.Loading
            try {
                detail = Loadable.Ready(IrisLink.api().send("GET",
                    "/personal-insights/${Uri.encode(insight.id)}?range=$range", null, InsightDetail.serializer()))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { detail = Loadable.Failed(e.message ?: "Current evidence unavailable.") }
        }
    }
    IrisCard(Modifier.fillMaxWidth()) {
        Kicker(insightKind(insight.kind))
        Text(insight.title, fontFamily = Serif, fontSize = 18.sp, color = colors.ink)
        ClauseText("What you wrote", insight.observation)
        Kicker("One possible explanation")
        Text(insight.possibleMeaning.text, color = colors.ink2)
        Kicker("Another possibility")
        Text(insight.alternative.text, color = colors.ink2)
        ClauseText("Immediate return", insight.immediateReturn)
        ClauseText("Later cost", insight.laterCost)
        if (insight.kind == "contextual_difference") Text(
            "${insight.leftLabel}: ${insight.leftGroupIds?.size ?: 0} groups · " +
            "${insight.rightLabel}: ${insight.rightGroupIds?.size ?: 0} groups", color = colors.ink3)
        Text(insight.question, color = colors.ink)
        if (!initiallyExpanded) TextButton(onClick = { onNavigate(insightRoute(insight.id, range)) }) {
            Text("Open insight detail")
        }
        insight.dynamicIds.forEach { id ->
            TextButton(onClick = { onNavigate(patternRoute(id, range)) }) { Text("Open involved pattern") }
        }
        TextButton(onClick = { onNavigate(insightDiscussionRoute(insight, range)) }) { Text("Explore with Iris") }
        TextButton(onClick = { expanded = !expanded }) { Text(if (expanded) "Hide evidence" else "See complete evidence") }
        if (expanded) when (val loaded = detail) {
            is Loadable.Loading -> LoadingState("Opening source accounts…")
            is Loadable.Failed -> ErrorState(loaded.message, onRetry = { request++ })
            is Loadable.Ready -> {
                val data = loaded.value
                data.insight.dynamicIds.forEach { dynamicId ->
                    Kicker("Pattern ${data.insight.dynamicIds.indexOf(dynamicId) + 1} · source groups")
                    data.groups[dynamicId].orEmpty().forEach { group ->
                        Text("${group.role} · ${if (group.independentlyCountable) "independent" else "independence uncertain"}",
                            color = colors.ink3, fontSize = 12.sp)
                        group.accountIds.forEach { accountId ->
                            data.accounts[accountId]?.let { AccountExcerpt(it, onNavigate) }
                        }
                    }
                    data.memberships[dynamicId].orEmpty().filter { member ->
                        data.groups[dynamicId].orEmpty().none { member.accountId in it.accountIds }
                    }.forEach { member ->
                        Text("${member.role}${if (member.excluded) " · your correction" else ""}", color = colors.ink3)
                        data.accounts[member.accountId]?.let { AccountExcerpt(it, onNavigate) }
                    }
                }
                val visible = data.memberships.values.flatten().map { it.accountId }.toSet()
                data.insight.unknownAccountIds.filterNot { it in visible }.forEach { accountId ->
                    data.accounts[accountId]?.let {
                        Kicker("Unclear account")
                        AccountExcerpt(it, onNavigate)
                    }
                }
            }
        }
        if (insight.feedback?.needsReview == true) Text("Saved opinion needs review: evidence changed.", color = colors.ink3)
        FeedbackForm("insight/${insight.id}", PATTERN_VERDICTS, insight.feedback?.verdict,
            insight.feedback?.note, enabled, error) { verdict, note -> onJudge(insight, verdict, note) }
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
                            TextButton(onClick = { onNavigate("journal?entry=${Uri.encode(id)}") }) { Text("Open check-in") }
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
