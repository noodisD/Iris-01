package com.iris.android.ui.more

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iris.android.R
import com.iris.android.api.IrisLink
import com.iris.android.api.User
import com.iris.android.ui.components.IrisCard
import com.iris.android.ui.components.IrisOrb
import com.iris.android.ui.components.IrisScaffold
import com.iris.android.ui.components.Kicker
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif

@Composable
fun MoreScreen(onNavigate: (String) -> Unit) {
    var user by remember { mutableStateOf<User?>(null) }
    val colors = LocalIrisColors.current
    LaunchedEffect(Unit) {
        user = runCatching { IrisLink.api().send("GET", "/user", null, User.serializer()) }.getOrNull()
    }
    val destinations = listOf(
        Triple("Insights", R.drawable.ic_insights, "insights"),
        Triple("Patterns", R.drawable.ic_repeat, "patterns"),
        Triple("Noticed", R.drawable.ic_visibility, "noticed"),
        Triple("Review", R.drawable.ic_mail, "review"),
        Triple("Import", R.drawable.ic_upload_file, "import"),
        Triple("Sensors", R.drawable.ic_sensors, "sensors"),
        Triple("Settings", R.drawable.ic_settings, "settings"),
    )
    IrisScaffold(title = "More") { padding ->
        LazyColumn(contentPadding = padding) {
            item {
                IrisCard(Modifier.fillMaxWidth().padding(20.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        IrisOrb()
                        Column {
                            Text("Iris", fontFamily = Serif, fontSize = 22.sp, color = colors.ink)
                            Kicker("v.0${user?.let { " · day ${it.dayInJourney}" } ?: ""}")
                            user?.name?.takeIf { it.isNotBlank() }?.let { Text(it, color = colors.ink2) }
                        }
                    }
                }
            }
            items(destinations.size) { index ->
                val (label, icon, route) = destinations[index]
                HubRow(label, icon, onClick = { onNavigate(route) })
            }
            item { HorizontalDivider(color = colors.lineSoft, modifier = Modifier.padding(horizontal = 20.dp)) }
            item { HubRow("Phone collector", R.drawable.ic_phone_android) { onNavigate("collector") } }
            item { HubRow("↺ Re-meet Iris", R.drawable.ic_replay) { onNavigate("onboarding") } }
        }
    }
}

@Composable
private fun HubRow(label: String, icon: Int, onClick: () -> Unit) {
    val colors = LocalIrisColors.current
    ListItem(
        headlineContent = { Text(label, color = colors.ink) },
        leadingContent = { Icon(painterResource(icon), contentDescription = null) },
        trailingContent = { Icon(painterResource(R.drawable.ic_expand_more), contentDescription = null,
            modifier = Modifier.rotate(-90f)) },
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 8.dp),
        colors = androidx.compose.material3.ListItemDefaults.colors(containerColor = colors.bg0),
    )
}
