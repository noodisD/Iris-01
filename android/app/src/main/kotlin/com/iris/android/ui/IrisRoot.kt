package com.iris.android.ui

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.iris.android.HomeNetwork
import com.iris.android.R
import com.iris.android.api.IrisLink
import com.iris.android.ui.components.IrisOrb
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.launch

@Composable
fun IrisRoot(
    locked: Boolean, lockMessage: String?, lockNeedsSetup: Boolean, onUnlock: () -> Unit,
    pendingDestination: String?, onDestinationHandled: () -> Unit,
) {
    if (locked) {
        LockScreen(lockMessage, lockNeedsSetup, onUnlock)
        return // No navigation tree or journal data is composed behind the lock.
    }
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { IrisLink.refresh(context) }
    DisposableEffect(lifecycle, context) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_START) scope.launch { IrisLink.refresh(context) }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    DisposableEffect(context) {
        val manager = context.getSystemService(ConnectivityManager::class.java)
        val request = HomeNetwork.request()
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { scope.launch { IrisLink.refresh(context) } }
            override fun onLost(network: Network) { scope.launch { IrisLink.refresh(context) } }
        }
        manager.registerNetworkCallback(request, callback)
        onDispose { manager.unregisterNetworkCallback(callback) }
    }
    IrisNavHost(pendingDestination, onDestinationHandled)
}

@Composable
private fun LockScreen(message: String?, needsSetup: Boolean, onUnlock: () -> Unit) {
    val colors = LocalIrisColors.current
    val context = LocalContext.current
    Column(Modifier.fillMaxSize().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center) {
        IrisOrb(56.dp)
        Text("IRIS is locked", fontFamily = Serif, fontSize = 34.sp, color = colors.ink,
            modifier = Modifier.padding(top = 24.dp))
        Text("Unlock with your fingerprint or screen lock.", color = colors.ink2,
            modifier = Modifier.padding(top = 12.dp, bottom = 24.dp))
        Button(onClick = {
            if (needsSetup) context.startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS))
            else onUnlock()
        }) {
            Icon(painterResource(R.drawable.ic_fingerprint), contentDescription = null,
                modifier = Modifier.padding(end = 8.dp))
            Text(if (needsSetup) "Open security settings" else "Unlock")
        }
        if (message != null) Text(message, color = colors.rose,
            modifier = Modifier.padding(top = 16.dp))
    }
}
