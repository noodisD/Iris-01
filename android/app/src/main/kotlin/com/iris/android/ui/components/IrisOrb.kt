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
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * The lens's colours per screen, the same five palettes as the web app
 * (frontend/src/hooks/useIrisState.ts, applyOrbVibe): inner light, iris,
 * outer ring, glow, and how fast the pupil breathes.
 */
enum class OrbVibe(val hueA: Color, val hueB: Color, val hueC: Color, val glow: Color, val rateMs: Int) {
    Calm(Color(0xFFD6D0FF), Color(0xFF8B7FD6), Color(0xFF3D3570), Color(0x598B7FD6), 4000),
    Low(Color(0xFFF0CFE0), Color(0xFFB784B8), Color(0xFF4F3050), Color(0x59B784B8), 6500),
    High(Color(0xFFF6E6B8), Color(0xFFC9A2D8), Color(0xFF5A3F6E), Color(0x4DE3C26B), 2400),
    Cool(Color(0xFFD4DCFF), Color(0xFF7F93DC), Color(0xFF2F3A6E), Color(0x597F93DC), 5500),
    Dim(Color(0xFF6A6788), Color(0xFF3F3D5C), Color(0xFF22213A), Color(0x40504E78), 7000),
}

val LocalOrbVibe = staticCompositionLocalOf { OrbVibe.Calm }

private val PUPIL = Color(0xFF0C0B18)
private val FIBRE = Color(0x38FFFFFF)
private val GLINT = Color(0x8CFFFFFF)

/**
 * The Lens, IRIS's mark, drawn as on the web (frontend/src/ui/Lens.tsx) and in
 * the launcher icon: a violet iris with fine fibres, a dark pupil that breathes
 * slowly, and a glint. Proportions are the web's 40-unit drawing.
 */
@Composable
fun IrisOrb(size: Dp = 22.dp, modifier: Modifier = Modifier) {
    val vibe = LocalOrbVibe.current
    val a = animateColorAsState(vibe.hueA, tween(800), label = "lens hue a").value
    val b = animateColorAsState(vibe.hueB, tween(800), label = "lens hue b").value
    val c = animateColorAsState(vibe.hueC, tween(800), label = "lens hue c").value
    val glow = animateColorAsState(vibe.glow, tween(800), label = "lens glow").value
    val breathe = rememberInfiniteTransition(label = "lens breathe")
    val pupil by breathe.animateFloat(1f, 0.82f,
        infiniteRepeatable(tween(vibe.rateMs / 2), RepeatMode.Reverse), label = "pupil")
    Canvas(modifier.size(size)) {
        val r = this.size.minDimension / 2f
        val unit = r / 19f   // one unit of the web's 40-unit lens (iris radius 19)
        // The glow, the web's drop-shadow.
        drawCircle(Brush.radialGradient(listOf(glow, Color.Transparent), center = center, radius = r * 1.3f),
            radius = r * 1.3f)
        drawCircle(Brush.radialGradient(0f to a, 0.55f to b, 1f to c, center = center, radius = r), radius = r)
        if (size >= 18.dp) {
            // Fibres are hairlines; below this size they only muddy the iris.
            for (i in 0 until 24) {
                rotate(i * 15f) {
                    drawLine(FIBRE, Offset(center.x, center.y - 11 * unit), Offset(center.x, center.y - 17 * unit),
                        strokeWidth = (0.6f * unit).coerceAtLeast(0.8f), cap = StrokeCap.Round)
                }
            }
        }
        drawCircle(PUPIL, radius = 7 * unit * pupil)
        drawCircle(GLINT, radius = 1.6f * unit, center = Offset(center.x - 3 * unit, center.y - 3.5f * unit))
    }
}
