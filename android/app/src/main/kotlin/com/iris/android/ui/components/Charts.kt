package com.iris.android.ui.components

import android.graphics.Paint
import android.graphics.Typeface
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.dp
import com.iris.android.api.InsightSeries
import com.iris.android.ui.habits.habitColor
import com.iris.android.ui.theme.LocalIrisColors

/** Geometry matches the web's twin-series plot, scaled only along its x axis. */
@Composable
fun TwinSeriesChart(series: List<InsightSeries>, modifier: Modifier = Modifier) {
    val colors = LocalIrisColors.current
    val all = series.flatMap { item -> item.points.map { it.y } }
    val minimum = all.minOrNull() ?: 0.0
    val span = ((all.maxOrNull() ?: minimum) - minimum).takeIf { it != 0.0 } ?: 1.0
    Canvas(modifier.fillMaxWidth().height(220.dp)) {
        val unit = density
        val width = size.width
        fun x(index: Int, count: Int): Float = if (count > 1) width * index / (count - 1) else width / 2
        fun y(value: Double): Float = (20 + (1 - (value - minimum) / span) * 180).toFloat() * unit
        val guideDash = PathEffect.dashPathEffect(floatArrayOf(2 * unit, 4 * unit))
        for (guide in 0..4) {
            val ordinate = (20 + 45 * guide) * unit
            drawLine(colors.lineSoft, Offset(0f, ordinate), Offset(width, ordinate),
                pathEffect = guideDash)
        }
        val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = Typeface.MONOSPACE
            textSize = 9 * unit
        }
        series.forEachIndexed { index, item ->
            val ink = habitColor(item.color)
            val points = item.points
            if (points.size > 1) {
                val path = Path().apply {
                    moveTo(x(0, points.size), y(points[0].y))
                    for (i in 1 until points.size) lineTo(x(i, points.size), y(points[i].y))
                }
                drawPath(path, ink, style = Stroke(width = 1.8f * unit, cap = StrokeCap.Round,
                    pathEffect = if (index == 1) PathEffect.dashPathEffect(floatArrayOf(4 * unit, 3 * unit)) else null))
            }
            points.forEachIndexed { i, point -> drawCircle(ink, radius = 2.5f * unit, center = Offset(x(i, points.size), y(point.y))) }
            labelPaint.color = ink.toArgb()
            drawContext.canvas.nativeCanvas.drawText("${if (index == 0) "—" else "---"} ${item.name.uppercase()}",
                (6 + 120 * index) * unit, 14 * unit, labelPaint)
        }
    }
}

