package com.iris.android.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.iris.android.api.IrisLink
import com.iris.android.api.User
import com.iris.android.ui.components.IrisOrb
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

@Composable
fun OnboardingScreen(onComplete: () -> Unit) {
    val model: OnboardingViewModel = viewModel()
    val busy by model.busy.collectAsState()
    val error by model.error.collectAsState()
    val colors = LocalIrisColors.current
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Column(Modifier.widthIn(max = 460.dp), horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp)) {
            IrisOrb(56.dp)
            Text(buildAnnotatedString {
                append("Hi. I'm ")
                pushStyle(SpanStyle(color = colors.sage, fontStyle = FontStyle.Italic))
                append("Iris")
                pop()
                append(".")
            }, fontFamily = Serif, fontSize = 44.sp, lineHeight = 48.sp, color = colors.ink,
                textAlign = TextAlign.Center)
            Text("Three things before we start. I run on this machine and everything I store stays in " +
                "your own database — though what you write is sent to OpenAI to be turned into " +
                "embeddings and replies. I need about a week of entries before I notice anything worth " +
                "saying. And everything I come to believe about you is visible, and removable, in Settings.",
                fontFamily = Serif, fontSize = 17.sp, lineHeight = 26.sp, color = colors.ink2,
                textAlign = TextAlign.Center)
            Button(onClick = { model.complete(onComplete) }, enabled = !busy) {
                Text(if (busy) "One moment…" else "Yes — let's start →")
            }
            if (error != null) {
                Text("Couldn't start: $error", style = IrisType.mono.copy(fontSize = 13.sp),
                    color = colors.rose, textAlign = TextAlign.Center)
            }
        }
    }
}

class OnboardingViewModel : ViewModel() {
    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    fun complete(onComplete: () -> Unit) {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                IrisLink.api().send("POST", "/onboarding/complete", null, User.serializer())
                onComplete()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                _error.value = error.message ?: error.toString()
            } finally {
                _busy.value = false
            }
        }
    }
}
