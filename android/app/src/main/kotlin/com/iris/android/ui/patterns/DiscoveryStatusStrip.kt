package com.iris.android.ui.patterns

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import com.iris.android.api.DiscoveryStatus
import com.iris.android.api.IrisLink
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

@Serializable
private data class DiscoveryRefreshResult(val queuedEntries: Int, val queuedSynthesis: Boolean)

/** Poll while reading or synthesis is active; show unavailable analysis separately from ready-empty. */
@Composable
internal fun DiscoveryStatusStrip(onCompletion: () -> Unit = {}) {
    val owner = LocalLifecycleOwner.current
    val latestCompletion by rememberUpdatedState(onCompletion)
    val colors = LocalIrisColors.current
    var status by remember { mutableStateOf<DiscoveryStatus?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refresh by remember { mutableIntStateOf(0) }
    var requesting by remember { mutableStateOf(false) }
    val coroutineScope = rememberCoroutineScope()
    fun request(scope: String) {
        requesting = true
        coroutineScope.launch {
            try {
                IrisLink.api().send("POST", "/discovery/refresh",
                    buildJsonObject { put("scope", scope) }.toString(), DiscoveryRefreshResult.serializer())
                refresh++
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { error = e.message ?: "Reading request failed. Try again." }
            finally { requesting = false }
        }
    }
    LaunchedEffect(owner, refresh) {
        owner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                try {
                    val next = IrisLink.api().send("GET", "/discovery/status", null, DiscoveryStatus.serializer())
                    val previous = status
                    status = next
                    error = null
                    if (previous != null && (previous.currentEntries != next.currentEntries ||
                            previous.stage != next.stage || previous.lastCompletedAt != next.lastCompletedAt)) latestCompletion()
                    if (next.pendingEntries == 0 && !next.synthesisPending) awaitCancellation()
                    delay(5_000)
                } catch (e: CancellationException) { throw e }
                catch (e: Exception) {
                    error = e.message ?: "Reading status unavailable."
                    awaitCancellation()
                }
            }
        }
    }
    Column {
        status?.let { s ->
            Text("Discovery: ${s.stage} · ${s.currentEntries}/${s.eligibleEntries} entries read · " +
                "${s.pendingEntries} pending · ${s.failedEntries} failed" +
                if (s.synthesisPending) " · synthesis pending" else "",
                style = IrisType.mono, color = colors.ink3, fontSize = 12.sp)
            s.lastCompletedAt?.let { Text("Last completed: $it", color = colors.ink3, fontSize = 12.sp) }
            if (s.omittedAccounts > 0 || s.omittedFields > 0) Text(
                "${s.omittedAccounts} accounts and ${s.omittedFields} fields could not be grounded in sources.",
                color = colors.ink3, fontSize = 12.sp)
            if (s.unreadEntries > 0 || s.stage != "ready") {
                Text("Archive estimate (${s.model}): ${s.estimate.readingRequests} reading + " +
                    "${s.estimate.synthesisRequests} synthesis requests · ~${s.estimate.tokensIn} in / " +
                    "${s.estimate.tokensOut} out tokens · ${s.estimate.costText}",
                    color = colors.ink3, fontSize = 12.sp)
                if (s.unreadEntries > 0 || (s.currentEntries == s.eligibleEntries && !s.synthesisPending && !s.synthesisFailed)) {
                    TextButton(enabled = !requesting, onClick = { request("unread") }) {
                        Text("Read existing writing")
                    }
                }
            }
            if (s.failedEntries > 0 || s.synthesisFailed) TextButton(enabled = !requesting, onClick = { request("failed") }) {
                Text("Retry failed discovery")
            }
            if (s.stage == "ready" && s.currentEntries == s.eligibleEntries) {
                Text("Current writing checked. A ready view can still have no qualifying dynamics.",
                    color = colors.ink3, fontSize = 12.sp)
            }
        }
        error?.let {
            Text(it, color = colors.rose, fontSize = 12.sp)
            TextButton(onClick = { refresh++ }) { Text("Retry status") }
        }
    }
}
