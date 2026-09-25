package com.iris.android.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.iris.android.R
import com.iris.android.api.IrisLink
import com.iris.android.api.LinkState
import com.iris.android.ui.components.EmptyState
import com.iris.android.ui.components.LoadingState
import kotlinx.coroutines.launch

@Composable
fun Gated(onOpenCollector: () -> Unit, content: @Composable () -> Unit) {
    val state by IrisLink.state.collectAsState()
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val retry = { scope.launch { IrisLink.refresh(ctx) }; Unit }
    if (state is LinkState.Ready) { content(); return }
    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        when (val link = state) {
            null -> LoadingState("Connecting to IRIS…")
            LinkState.NotPaired -> EmptyState("Pair this phone with IRIS",
                "On your laptop open IRIS → Settings → Android live sensors, generate a pairing token, then scan it in Phone collector.") {
                Button(onClick = onOpenCollector) { Text("Open Phone collector") }
            }
            is LinkState.NoHomeWifi -> {
                Icon(painterResource(R.drawable.ic_wifi_off), contentDescription = null)
                EmptyState("Connect to your home Wi-Fi",
                    "IRIS runs on your laptop at ${link.host}. This phone reaches it only over the Wi-Fi network they share.") {
                    OutlinedButton(onClick = retry) { Text("Try again") }
                }
            }
            is LinkState.Refused -> EmptyState("IRIS refused this phone", link.message) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    OutlinedButton(onClick = retry) { Text("Try again") }
                    Button(onClick = onOpenCollector) { Text("Open Phone collector") }
                }
            }
            is LinkState.Unreachable -> EmptyState("Can't reach IRIS",
                link.message + "\nIs uv run python scripts/serve_iris.py running on the laptop?") {
                OutlinedButton(onClick = retry) { Text("Try again") }
            }
            is LinkState.Ready -> Unit
        }
    }
}
