package com.iris.android.api

import android.content.Context
import android.net.Network
import com.iris.android.HomeNetwork
import com.iris.android.IrisApiClient
import com.iris.android.IrisResponse
import com.iris.android.Settings
import com.iris.android.describe
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

sealed interface LinkState {
    data object NotPaired : LinkState
    data class NoHomeWifi(val host: String) : LinkState
    data class Refused(val message: String) : LinkState
    data class Unreachable(val message: String) : LinkState
    data class Ready(val api: IrisApi) : LinkState
}

object IrisLink {
    private val refreshLock = Mutex()
    private val _state = MutableStateFlow<LinkState?>(null)
    val state: StateFlow<LinkState?> = _state
    private var connectionKey: ConnectionKey? = null

    suspend fun refresh(ctx: Context) = refreshLock.withLock {
        val resolved = resolve(ctx.applicationContext)
        val sameConnection = connectionKey != null && resolved.key == connectionKey
        if (shouldReplaceLink(_state.value is LinkState.Ready, resolved.state is LinkState.Ready, sameConnection)) {
            _state.value = resolved.state
            connectionKey = resolved.key
        }
    }

    fun api(): IrisApi = (state.value as? LinkState.Ready)?.api
        ?: throw IrisApiException(0, "offline", "IRIS is not connected.")

    private suspend fun resolve(ctx: Context): Resolved {
        val host = Settings.laptopHost(ctx)
        if (!Settings.hasBearer(ctx) || host == null) return Resolved(LinkState.NotPaired, null)
        val bearer = try { Settings.bearer(ctx) } catch (error: IllegalStateException) {
            return Resolved(LinkState.Refused(error.message ?: "Stored pairing token is unreadable"), null)
        }
        val network = HomeNetwork.find(ctx, host) ?: return Resolved(LinkState.NoHomeWifi(host), null)
        val url = Settings.laptopBaseUrl(ctx)
        val pin = Settings.publicKeySha256(ctx)
        val key = ConnectionKey(url, pin, bearer, network)
        val response = withContext(Dispatchers.IO) {
            IrisApiClient(url, bearer, pin, network).checkConnection()
        }
        return when (response) {
            IrisResponse.Accepted -> Resolved(LinkState.Ready(IrisApi(url, bearer, pin, network)), key)
            is IrisResponse.Unreachable -> Resolved(LinkState.Unreachable(response.describe()), key)
            is IrisResponse.Blocked, is IrisResponse.Rejected -> Resolved(LinkState.Refused(response.describe()), key)
        }
    }

    private data class ConnectionKey(
        val baseUrl: String,
        val publicKeySha256: String,
        val bearer: String,
        val network: Network,
    )

    private class Resolved(val state: LinkState, val key: ConnectionKey?)
}
