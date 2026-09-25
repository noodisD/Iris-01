@file:OptIn(androidx.compose.ui.text.ExperimentalTextApi::class)
package com.iris.android.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.iris.android.R

val Serif = FontFamily(
    Font(R.font.instrument_serif_regular),
    Font(R.font.instrument_serif_italic, style = FontStyle.Italic),
)

private val weights = listOf(FontWeight.Light, FontWeight.Normal, FontWeight.Medium, FontWeight.SemiBold)
val Sans = FontFamily(*weights.map { weight ->
    Font(R.font.geist, weight = weight, variationSettings = FontVariation.Settings(FontVariation.weight(weight.weight)))
}.toTypedArray())
val Mono = FontFamily(*weights.map { weight ->
    Font(R.font.geist_mono, weight = weight, variationSettings = FontVariation.Settings(FontVariation.weight(weight.weight)))
}.toTypedArray())

private val default = Typography()
val IrisTypography = Typography(
    displayLarge = default.displayLarge.copy(fontFamily = Serif, fontWeight = FontWeight.Normal),
    displayMedium = default.displayMedium.copy(fontFamily = Serif, fontWeight = FontWeight.Normal),
    displaySmall = default.displaySmall.copy(fontFamily = Serif, fontWeight = FontWeight.Normal),
    headlineLarge = default.headlineLarge.copy(fontFamily = Serif, fontWeight = FontWeight.Normal),
    headlineMedium = default.headlineMedium.copy(fontFamily = Serif, fontWeight = FontWeight.Normal),
    headlineSmall = default.headlineSmall.copy(fontFamily = Serif, fontWeight = FontWeight.Normal),
    titleLarge = default.titleLarge.copy(fontFamily = Serif, fontWeight = FontWeight.Normal),
    titleMedium = default.titleMedium.copy(fontFamily = Sans),
    titleSmall = default.titleSmall.copy(fontFamily = Sans),
    bodyLarge = default.bodyLarge.copy(fontFamily = Sans, fontSize = 15.sp),
    bodyMedium = default.bodyMedium.copy(fontFamily = Sans, fontSize = 15.sp),
    bodySmall = default.bodySmall.copy(fontFamily = Sans),
    labelLarge = default.labelLarge.copy(fontFamily = Sans),
    labelMedium = default.labelMedium.copy(fontFamily = Sans),
    labelSmall = default.labelSmall.copy(fontFamily = Sans),
)

object IrisType {
    val kicker = TextStyle(fontFamily = Mono, fontSize = 10.5.sp, letterSpacing = 1.9.sp)
    val mono = TextStyle(fontFamily = Mono, fontSize = 11.sp, letterSpacing = 0.9.sp)
}
