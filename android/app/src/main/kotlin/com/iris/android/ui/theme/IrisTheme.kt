package com.iris.android.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.unit.dp

@Composable
fun IrisTheme(content: @Composable () -> Unit) {
    val c = IrisPalette
    CompositionLocalProvider(LocalIrisColors provides c) {
        MaterialTheme(
            colorScheme = darkColorScheme(
                primary = c.sage, onPrimary = c.bg1, primaryContainer = c.sageDim,
                onPrimaryContainer = c.ink, secondary = c.amber, onSecondary = c.bg1,
                tertiary = c.indigo, onTertiary = c.bg1, error = c.rose, onError = c.bg1,
                background = c.bg0, onBackground = c.ink, surface = c.bg0, onSurface = c.ink,
                surfaceVariant = c.bg2, onSurfaceVariant = c.ink2,
                surfaceContainerLowest = c.bg0, surfaceContainerLow = c.bg1,
                surfaceContainer = c.bg2, surfaceContainerHigh = c.bg3,
                surfaceContainerHighest = c.line, outline = c.line, outlineVariant = c.lineSoft,
            ),
            typography = IrisTypography,
            shapes = Shapes(
                extraSmall = RoundedCornerShape(6.dp), small = RoundedCornerShape(10.dp),
                medium = RoundedCornerShape(16.dp), large = RoundedCornerShape(24.dp),
                extraLarge = RoundedCornerShape(28.dp),
            ),
            content = content,
        )
    }
}
