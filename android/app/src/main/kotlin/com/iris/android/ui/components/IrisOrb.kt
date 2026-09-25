package com.iris.android.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** Palettes follow the web app's route-default orb states. */
enum class OrbVibe(val hueA: Color, val hueB: Color, val hueC: Color, val glow: Color, val rateMs: Int) {
    Calm(Color(0xFFD8EFD2), Color(0xFFA9C8A3), Color(0xFF6F8C6A), Color(0x59A9C8A3), 4000),
    Low(Color(0xFFF3D4D4), Color(0xFFD48A8A), Color(0xFFA06868), Color(0x66D48A8A), 6500),
    High(Color(0xFFF4DCB8), Color(0xFFD4A374), Color(0xFFA07A55), Color(0x73D4A374), 2400),
    Cool(Color(0xFFDBE0F0), Color(0xFF9AA3D4), Color(0xFF6F78A0), Color(0x599AA3D4), 5500),
    Dim(Color(0xFF3A3A30), Color(0xFF2A2A22), Color(0xFF1A1A14), Color(0x4D504C40), 7000),
}

val LocalOrbVibe = staticCompositionLocalOf { OrbVibe.Calm }

@Composable
fun IrisOrb(size: Dp = 22.dp, modifier: Modifier = Modifier) {
    val vibe = LocalOrbVibe.current
    val a = animateColorAsState(vibe.hueA, tween(800), label = "orb hue a").value
    val b = animateColorAsState(vibe.hueB, tween(800), label = "orb hue b").value
    val c = animateColorAsState(vibe.hueC, tween(800), label = "orb hue c").value
    val glow = animateColorAsState(vibe.glow, tween(800), label = "orb glow").value
    val breathe = rememberInfiniteTransition(label = "orb breathe")
    val scale by breathe.animateFloat(1f, 1.06f, infiniteRepeatable(tween(vibe.rateMs / 2), RepeatMode.Reverse), label = "orb scale")
    val alpha by breathe.animateFloat(0.9f, 1f, infiniteRepeatable(tween(vibe.rateMs / 2), RepeatMode.Reverse), label = "orb alpha")
    Canvas(modifier.size(size)) {
        val radius = this.size.minDimension / 2f
        scale(scale) {
            drawCircle(
                Brush.radialGradient(listOf(glow.copy(alpha = glow.alpha * alpha), Color.Transparent),
                    center = center, radius = radius * 1.25f),
                radius = radius * 1.25f,
            )
            drawCircle(
                Brush.radialGradient(
                    colorStops = arrayOf(0f to a, .55f to b, 1f to c),
                    center = Offset(this.size.width * .35f, this.size.height * .3f),
                    radius = radius * 1.8f,
                ),
                radius = radius, alpha = alpha,
            )
        }
    }
}
