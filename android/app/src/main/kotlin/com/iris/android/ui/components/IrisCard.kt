package com.iris.android.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.iris.android.ui.theme.IrisType
import com.iris.android.ui.theme.LocalIrisColors

@Composable
fun Kicker(text: String, modifier: Modifier = Modifier, color: Color = LocalIrisColors.current.ink3) {
    Text(text.uppercase(), modifier, style = IrisType.kicker, color = color)
}

@Composable
fun IrisCard(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    val colors = LocalIrisColors.current
    val shape = androidx.compose.material3.MaterialTheme.shapes.medium
    val cardColors = CardDefaults.cardColors(containerColor = colors.bg2)
    if (onClick == null) Card(modifier, shape = shape, colors = cardColors,
        border = BorderStroke(1.dp, colors.lineSoft)) {
        Column(Modifier.padding(16.dp), content = content)
    } else Card(onClick = onClick, modifier = modifier, shape = shape, colors = cardColors,
        border = BorderStroke(1.dp, colors.lineSoft)) {
        Column(Modifier.padding(16.dp), content = content)
    }
}

@Composable
fun Tag(text: String, color: Color = LocalIrisColors.current.ink3) {
    val colors = LocalIrisColors.current
    androidx.compose.material3.Surface(shape = androidx.compose.foundation.shape.RoundedCornerShape(50),
        color = Color.Transparent, border = BorderStroke(1.dp, colors.line)) {
        Text(text.uppercase(), Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            style = IrisType.mono, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}
