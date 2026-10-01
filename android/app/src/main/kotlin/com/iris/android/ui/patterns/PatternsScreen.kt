@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.iris.android.ui.patterns

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.ui.platform.LocalLifecycleOwner
import com.iris.android.api.ACCOUNT_VERDICTS
import com.iris.android.api.DISCOVERY_RANGES
import com.iris.android.api.GroundedClause
import com.iris.android.api.IrisLink
import com.iris.android.api.Ok
import com.iris.android.api.PATTERN_VERDICTS
import com.iris.android.api.PatternDetail
import com.iris.android.api.PatternMembership
import com.iris.android.api.PatternsResponse
import com.iris.android.api.PersonalPattern
import com.iris.android.api.SavedFeedback
import com.iris.android.api.SourceAccount
import com.iris.android.api.SourceCitation
import com.iris.android.api.patternDiscussionRoute
import com.iris.android.api.patternRoute
import com.iris.android.ui.Loadable
import com.iris.android.ui.components.ErrorState
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.components.LoadingState
import com.iris.android.ui.components.RefreshableList
import com.iris.android.ui.formatEventDate
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

private val RANGE_OPTIONS = listOf("all" to "All available writing", "30d" to "30d", "90d" to "90d")

class PatternsViewModel(private val savedStateHandle: SavedStateHandle) : ViewModel() {
    val range = savedStateHandle.getStateFlow("range", "all")
    private val _patterns = MutableStateFlow<Loadable<PatternsResponse>>(Loadable.Loading)
    val patterns = _patterns.asStateFlow()
    private val _refreshing = MutableStateFlow(false)
    val refreshing = _refreshing.asStateFlow()
    private var generation = 0

    fun refresh() {
        val version = ++generation
        val selected = range.value
        viewModelScope.launch {
            _refreshing.value = true
            try {
                require(selected in DISCOVERY_RANGES)
                val result = IrisLink.api().send("GET", "/patterns?range=$selected", null, PatternsResponse.serializer())
                if (version == generation) _patterns.value = Loadable.Ready(result)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (version == generation) _patterns.value = Loadable.Failed(e.message ?: "Patterns unavailable.")
            } finally { if (version == generation) _refreshing.value = false }
        }
    }
}

@Composable
fun PatternsScreen(onNavigate: (String) -> Unit) {
    val vm: PatternsViewModel = viewModel()
    val state by vm.patterns.collectAsState()
    val range by vm.range.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val colors = LocalIrisColors.current
    RefreshOnReturn(range, vm::refresh)
    IrisScaffold(title = "Patterns", kicker = "from your writing") { padding ->
        RefreshableList(refreshing, vm::refresh) {
            LazyColumn(Modifier.fillMaxWidth().padding(padding),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    RangeChoices(range) { onNavigate("patterns?range=$it") }
                    DiscoveryStatusStrip(onCompletion = vm::refresh)
                }
                when (val s = state) {
                    is Loadable.Loading -> item { LoadingState("Opening your writing…") }
                    is Loadable.Failed -> item { ErrorState(s.message, onRetry = vm::refresh) }
                    is Loadable.Ready -> {
                        if (s.value.status.stage != "ready") item {
                            Text("Personal discovery is ${s.value.status.stage}. The current view is unavailable.", color = colors.ink3)
                        } else if (s.value.patterns.isEmpty()) item {
                            Text("No checked recurring dynamic was found in this range of writing. This does not mean you have none.", color = colors.ink3)
                        } else {
                            items(s.value.patterns, key = { it.id }) { PatternPreview(it, range, onNavigate) }
                        }
                    }
                }
            }
        }
    }
}

internal fun evidenceLabel(state: String) = when (state) {
    "owner_described" -> "You described this"
    "emerging" -> "Emerging in your writing"
    "recurring" -> "Recurring in your writing"
    else -> state
}

@Composable
private fun PatternPreview(p: PersonalPattern, range: String, onNavigate: (String) -> Unit) {
    val colors = LocalIrisColors.current
    IrisCard(Modifier.fillMaxWidth()) {
        Kicker(evidenceLabel(p.evidenceState))
        Text(p.title, fontFamily = Serif, fontSize = 19.sp, color = colors.ink)
        Text("${p.context.text} → ${p.response.text}", fontSize = 14.sp, color = colors.ink2)
        Text("At least ${p.independentGroupCount} distinct occasions identified / ${p.accountCount} accounts",
            color = colors.ink3, fontSize = 12.sp)
        Text("Recorded ${p.recordedFrom ?: "date unknown"} – ${p.recordedTo ?: "date unknown"}",
            color = colors.ink3, fontSize = 12.sp)
        p.example?.let { example ->
            Text("“${example.citation.text}”", color = colors.ink2, fontStyle = FontStyle.Italic, fontSize = 13.sp)
            CitationLink(example.citation, onNavigate)
        }
        if (p.feedback?.needsReview == true) Text("Saved opinion needs review: evidence changed.", color = colors.ink3)
        TextButton(onClick = { onNavigate(patternRoute(p.id, range)) }) { Text("What you wrote") }
        TextButton(onClick = { onNavigate(patternDiscussionRoute(p, range)) }) { Text("Explore with Iris") }
    }
}

class PatternDetailViewModel(private val savedStateHandle: SavedStateHandle) : ViewModel() {
    val range = savedStateHandle.getStateFlow("range", "all")
    private val _detail = MutableStateFlow<Loadable<PatternDetail>>(Loadable.Loading)
    val detail = _detail.asStateFlow()
    private val _saving = MutableStateFlow(false)
    val saving = _saving.asStateFlow()
    private val _error = MutableStateFlow<Pair<String, String>?>(null)
    val error = _error.asStateFlow()
    private var loadedId: String? = null
    private var generation = 0

    fun refresh(id: String) {
        val version = ++generation
        val selected = range.value
        if (loadedId != id) { loadedId = id; _detail.value = Loadable.Loading }
        viewModelScope.launch {
            try {
                require(selected in DISCOVERY_RANGES)
                val result = IrisLink.api().send("GET", "/patterns/${Uri.encode(id)}?range=$selected",
                    null, PatternDetail.serializer())
                if (version == generation) _detail.value = Loadable.Ready(result)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (version == generation) _detail.value = Loadable.Failed(e.message ?: "Current evidence unavailable. Return to Patterns.")
            }
        }
    }

    fun setPatternVerdict(id: String, verdict: String?, note: String?) =
        save(id, "pattern", "/patterns/${Uri.encode(id)}/verdict", verdict, note, false)

    fun setAccountFeedback(id: String, accountId: String, verdict: String?, note: String?) =
        save(id, accountId, "/patterns/${Uri.encode(id)}/accounts/${Uri.encode(accountId)}", verdict, note, true)

    private fun save(id: String, key: String, path: String, verdict: String?, note: String?, account: Boolean) {
        viewModelScope.launch {
            if (_saving.value) return@launch
            val current = (_detail.value as? Loadable.Ready)?.value ?: return@launch
            _saving.value = true
            _error.value = null
            generation++
            try {
                val body = buildJsonObject {
                    put("range", range.value); put("snapshot", current.snapshot)
                    put("verdict", verdict); put("note", note)
                }.toString()
                if (account) IrisLink.api().send("PUT", path, body, Ok.serializer())
                else IrisLink.api().send("PUT", path, body, SavedFeedback.serializer())
                refresh(id)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                _error.value = key to (e.message ?: "That didn't save. Review current evidence and retry.")
                refresh(id)
            } finally { _saving.value = false }
        }
    }
}

@Composable
fun PatternDetailScreen(id: String, onNavigate: (String) -> Unit, onBack: () -> Unit) {
    val vm: PatternDetailViewModel = viewModel()
    val state by vm.detail.collectAsState()
    val range by vm.range.collectAsState()
    val saving by vm.saving.collectAsState()
    val error by vm.error.collectAsState()
    val colors = LocalIrisColors.current
    RefreshOnReturn("$id/$range") { vm.refresh(id) }
    val detail = (state as? Loadable.Ready)?.value
    IrisScaffold(title = detail?.pattern?.title ?: "Pattern", kicker = "your recorded situations", onBack = onBack) { padding ->
        LazyColumn(Modifier.fillMaxWidth().padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            item { DiscoveryStatusStrip(onCompletion = { vm.refresh(id) }) }
            when (val s = state) {
                is Loadable.Loading -> item { LoadingState("Opening source accounts…") }
                is Loadable.Failed -> item {
                    ErrorState(s.message, onRetry = { vm.refresh(id) })
                    TextButton(onClick = { onNavigate("patterns?range=$range") }) { Text("Current patterns") }
                }
                is Loadable.Ready -> {
                    val d = s.value
                    val p = d.pattern
                    val members = d.memberships[id].orEmpty()
                    item {
                        RangeChoices(range) { onNavigate(patternRoute(id, it)) }
                        Kicker(evidenceLabel(p.evidenceState))
                        Text("At least ${p.independentGroupCount} distinct occasions identified / ${p.accountCount} accounts",
                            color = colors.ink2)
                        Text("Recorded ${p.recordedFrom ?: "date unknown"} – ${p.recordedTo ?: "date unknown"}", color = colors.ink3)
                        Text("${d.coverage.accountCount} accounts considered in this range; ${d.coverage.undatedAccountCount} undated",
                            color = colors.ink3, fontSize = 12.sp)
                    }
                    item {
                        Kicker("What you wrote")
                        ClauseText("Context", p.context)
                        ClauseText("Response", p.response)
                        p.ownerMeanings.forEach { ClauseText("You wrote", it) }
                        Kicker(if (p.evidenceState == "owner_described") "You described this"
                            else "What seems to recur")
                        Text(if (p.evidenceState == "owner_described")
                            "You described a context–response relationship; separate recurring events are not established."
                            else "At least ${p.independentGroupCount} distinct occasions identified; ${p.exceptionCount} recorded exceptions. " +
                                "Entry dates are writing dates, not event dates.", color = colors.ink2)
                        Kicker("One possible explanation")
                        Text(p.possibleMeaning?.text ?: "Not recorded enough to suggest one.", color = colors.ink2)
                        Kicker("Another possibility")
                        Text(p.alternative?.text ?: "Not recorded enough to distinguish another explanation.", color = colors.ink2)
                        Kicker("When it was different")
                        Text(if (p.exceptionGroupIds.isEmpty()) "No exception recorded in the checked writing"
                            else "${p.exceptionGroupIds.size} exception group(s); ${p.responseElsewhereGroupIds.size} response-elsewhere group(s).",
                            color = colors.ink2)
                        Text("${d.checks.checked} accounts checked; ${d.checks.unclear} unclear; " +
                            "${d.checks.omittedAccounts} accounts and ${d.checks.omittedFields} fields omitted. " +
                            (if (d.checks.exceptionSearchComplete) "Exception search completed in the checked writing."
                            else "Exception search is not complete."), color = colors.ink3, fontSize = 12.sp)
                        Kicker("What is not recorded")
                        ClauseText("Immediate return", p.immediateReturn)
                        ClauseText("Later cost", p.laterCost)
                        Text(p.openQuestion, color = colors.ink)
                    }
                    d.groups[id].orEmpty().forEach { group ->
                        val grouped = members.filter { it.groupId == group.id && !it.excluded && it.ownerVerdict != "no" }
                        if (grouped.isNotEmpty()) {
                            item(key = "group-${group.id}") {
                                Kicker("${group.role.replace('_', ' ')} · ${grouped.size} accounts" +
                                    if (group.independenceUncertain) " · independence uncertain"
                                    else if (group.independentlyCountable) " · independently identified"
                                    else " · not independently counted")
                            }
                            items(grouped, key = { "member-${it.accountId}" }) { member ->
                                d.accounts[member.accountId]?.let { account ->
                                    AccountCard(account, member, !saving, onNavigate,
                                        error?.takeIf { it.first == account.id }?.second) { verdict, note ->
                                        vm.setAccountFeedback(id, account.id, verdict, note)
                                    }
                                }
                            }
                        }
                    }
                    val groupedIds = d.groups[id].orEmpty().flatMap { it.accountIds }.toSet()
                    val ungrouped = members.filter { it.accountId !in groupedIds && !it.excluded && it.ownerVerdict != "no" }
                    if (ungrouped.isNotEmpty()) item { Kicker("Other checked accounts") }
                    items(ungrouped, key = { "other-${it.accountId}" }) { member ->
                        d.accounts[member.accountId]?.let { account ->
                            AccountCard(account, member, !saving, onNavigate,
                                error?.takeIf { it.first == account.id }?.second) { verdict, note ->
                                vm.setAccountFeedback(id, account.id, verdict, note)
                            }
                        }
                    }
                    if (members.any { it.excluded || it.ownerVerdict == "no" }) {
                        item { Kicker("Your corrections") }
                        items(members.filter { it.excluded || it.ownerVerdict == "no" }, key = { "excluded-${it.accountId}" }) { member ->
                            d.accounts[member.accountId]?.let { account ->
                                AccountCard(account, member, !saving, onNavigate,
                                    error?.takeIf { it.first == account.id }?.second) { verdict, note ->
                                    vm.setAccountFeedback(id, account.id, verdict, note)
                                }
                            }
                        }
                    }
                    item {
                        if (p.lensMatches.isNotEmpty()) {
                            var open by rememberSaveable(id) { mutableStateOf(false) }
                            TextButton(onClick = { open = !open }) { Text("A way to understand this (${p.lensMatches.size})") }
                            if (open) p.lensMatches.forEach { match ->
                                d.lenses.find { it.id == match.lensId }?.let { lens ->
                                    Kicker(lens.name)
                                    Text(lens.sequence, color = colors.ink2)
                                    Text("A possible function: ${lens.possibleFunction}", color = colors.ink3)
                                    Text("Another account: ${lens.alternative}", color = colors.ink3)
                                    Text(lens.question, color = colors.ink3)
                                    Text("An explanatory framework, not a classification of you.", color = colors.ink3, fontSize = 12.sp)
                                }
                            }
                        }
                        if (p.feedback?.needsReview == true) Text("Your saved opinion needs review: the evidence changed.", color = colors.ink2)
                        Kicker("Does this ring true?")
                        FeedbackForm(id, PATTERN_VERDICTS, p.feedback?.verdict, p.feedback?.note,
                            !saving, error?.takeIf { it.first == "pattern" }?.second) { verdict, note ->
                            vm.setPatternVerdict(id, verdict, note)
                        }
                        TextButton(onClick = { onNavigate(patternDiscussionRoute(p, range)) }) { Text("Explore with Iris") }
                    }
                }
            }
        }
    }
}

@Composable
internal fun ClauseText(label: String, clause: GroundedClause?) {
    val colors = LocalIrisColors.current
    Text("$label: ${clause?.text ?: "Not recorded"}", color = colors.ink2, fontSize = 14.sp)
}

@Composable
internal fun CitationLink(citation: SourceCitation, onNavigate: (String) -> Unit) {
    if (citation.sourceType == "reflection") TextButton(onClick = {
        onNavigate("journal?entry=${Uri.encode(citation.entryId)}")
    }) { Text("Open exact entry") }
}

@Composable
internal fun AccountExcerpt(account: SourceAccount, onNavigate: (String) -> Unit) {
    val colors = LocalIrisColors.current
    Text(account.recordedOn?.let { "Recorded ${formatEventDate(it)}" } ?: "Recorded date unknown",
        color = colors.ink3, fontSize = 12.sp)
    account.situation?.let { Text("Situation: $it", color = colors.ink2) }
    account.response?.let { Text("Response: $it", color = colors.ink2) }
    account.selfReport?.let { Text("You described: $it", color = colors.ink2) }
    account.immediateOutcome?.let { Text("Immediate: $it", color = colors.ink2) }
    account.laterOutcome?.let { Text("Later: $it", color = colors.ink2) }
    account.explanation?.let { Text("Your explanation: $it", color = colors.ink3, fontStyle = FontStyle.Italic) }
    account.citations.forEach { citation ->
        Text("“${citation.text}”", color = colors.ink3, fontStyle = FontStyle.Italic, fontSize = 13.sp)
        CitationLink(citation, onNavigate)
    }
}

@Composable
private fun AccountCard(account: SourceAccount, membership: PatternMembership,
                        enabled: Boolean, onNavigate: (String) -> Unit, error: String?,
                        onFeedback: (String?, String?) -> Unit) {
    val colors = LocalIrisColors.current
    IrisCard(Modifier.fillMaxWidth()) {
        Kicker(if (membership.excluded) "Excluded by your correction" else "${membership.role} · checked account")
        AccountExcerpt(account, onNavigate)
        FeedbackForm(account.id, ACCOUNT_VERDICTS, membership.ownerVerdict, membership.verdictNote,
            enabled, error, onFeedback)
        Text("This judges classification, not the words in your entry.", color = colors.ink3, fontSize = 12.sp)
    }
}

@Composable
internal fun RangeChoices(range: String, onSelect: (String) -> Unit) {
    Choices(RANGE_OPTIONS, range, true) { if (it != range) onSelect(it) }
}

@Composable
internal fun RefreshOnReturn(key: String, refresh: () -> Unit) {
    val owner = LocalLifecycleOwner.current
    val latestRefresh by rememberUpdatedState(refresh)
    LaunchedEffect(key) { latestRefresh() }
    DisposableEffect(owner, key) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) latestRefresh()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
}

@Composable
internal fun FeedbackForm(id: String, options: List<Pair<String, String>>, verdict: String?, note: String?,
                          enabled: Boolean, error: String?, onSave: (String?, String?) -> Unit) {
    val colors = LocalIrisColors.current
    var draftNote by rememberSaveable(id) { mutableStateOf(note.orEmpty()) }
    var draftVerdict by rememberSaveable(id) { mutableStateOf(verdict) }
    var serverNote by rememberSaveable(id) { mutableStateOf(note) }
    var serverVerdict by rememberSaveable(id) { mutableStateOf(verdict) }
    LaunchedEffect(note, verdict) {
        if (draftNote == serverNote.orEmpty()) draftNote = note.orEmpty()
        if (draftVerdict == serverVerdict) draftVerdict = verdict
        serverNote = note
        serverVerdict = verdict
    }
    Choices(options, draftVerdict, enabled) {
        draftVerdict = if (draftVerdict == it) null else it
        onSave(draftVerdict, draftNote)
    }
    OutlinedTextField(value = draftNote, onValueChange = { draftNote = it.take(1000) },
        label = { Text("Your note") }, enabled = enabled, modifier = Modifier.fillMaxWidth())
    TextButton(onClick = { onSave(draftVerdict, draftNote) }, enabled = enabled) { Text("Save note") }
    error?.let { Text(it, color = colors.rose, style = IrisType.mono) }
}

@Composable
internal fun Choices(options: List<Pair<String, String>>, current: String?, enabled: Boolean,
                     onPick: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (value, label) ->
            if (value == current) FilledTonalButton(onClick = { onPick(value) }, enabled = enabled) { Text(label) }
            else OutlinedButton(onClick = { onPick(value) }, enabled = enabled) { Text(label) }
        }
    }
}
