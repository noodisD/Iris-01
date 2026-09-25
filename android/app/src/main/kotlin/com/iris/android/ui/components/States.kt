package com.iris.android.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif

@Composable
fun LoadingState(label: String = "Iris is gathering your day…") {
    val colors = LocalIrisColors.current
    Column(Modifier.padding(vertical = 120.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(18.dp)) {
        IrisOrb()
        Text(label, fontFamily = Serif, fontStyle = FontStyle.Italic, fontSize = 20.sp, color = colors.ink2)
    }
}

@Composable
fun ErrorState(message: String? = null, onRetry: (() -> Unit)? = null) {
    val colors = LocalIrisColors.current
    Column(Modifier.padding(vertical = 100.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(14.dp)) {
        IrisOrb(modifier = Modifier.alpha(0.6f))
        Text("Something didn't load.", fontFamily = Serif, fontSize = 24.sp, color = colors.ink)
        Text(message ?: "Iris couldn't reach your data just now. Your information is safe — this is only the view.",
            fontSize = 13.sp, color = colors.ink3, textAlign = TextAlign.Center)
        if (onRetry != null) OutlinedButton(onClick = onRetry) { Text("Try again") }
    }
}

@Composable
fun EmptyState(title: String, body: String? = null, action: (@Composable () -> Unit)? = null) {
    val colors = LocalIrisColors.current
    Column(Modifier.padding(vertical = 90.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        IrisOrb(14.dp)
        Text(title, fontFamily = Serif, fontSize = 28.sp, color = colors.ink, textAlign = TextAlign.Center)
        if (body != null) Text(body, fontSize = 13.sp, color = colors.ink3, textAlign = TextAlign.Center)
        action?.invoke()
    }
}
