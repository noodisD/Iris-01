package com.iris.android.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

@Immutable
data class IrisColors(
    val bg0: Color, val bg1: Color, val bg2: Color, val bg3: Color,
    val line: Color, val lineSoft: Color, val ink: Color, val ink2: Color,
    val ink3: Color, val ink4: Color, val sage: Color, val sageDim: Color,
    val amber: Color, val rose: Color, val indigo: Color,
)

val IrisPalette = IrisColors(
    bg0 = Color(0xFF0E0E0C), bg1 = Color(0xFF14140F), bg2 = Color(0xFF1A1A14),
    bg3 = Color(0xFF232318), line = Color(0xFF2A2A1F), lineSoft = Color(0xFF1F1F17),
    ink = Color(0xFFE9E3D3), ink2 = Color(0xFFC2BBA8), ink3 = Color(0xFF807969),
    ink4 = Color(0xFF524D40), sage = Color(0xFFA9C8A3), sageDim = Color(0xFF6F8C6A),
    amber = Color(0xFFD4A374), rose = Color(0xFFD48A8A), indigo = Color(0xFF9AA3D4),
)

val LocalIrisColors = staticCompositionLocalOf { IrisPalette }
