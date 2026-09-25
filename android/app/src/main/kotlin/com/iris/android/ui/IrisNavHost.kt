@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.iris.android.ui

import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.res.painterResource
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import androidx.navigation.NavGraph.Companion.findStartDestination
import com.iris.android.R
import com.iris.android.api.IrisLink
import com.iris.android.api.LinkState
import com.iris.android.api.OnboardingState
import com.iris.android.ui.chat.ChatScreen
import com.iris.android.ui.habits.HabitsScreen
import com.iris.android.ui.insights.InsightsScreen
import com.iris.android.ui.insights.InsightDetailScreen
import com.iris.android.ui.journal.JournalScreen
import com.iris.android.ui.journal.JournalVoiceScreen
import com.iris.android.ui.importing.ImportScreen
import com.iris.android.ui.noticed.NoticedScreen
import com.iris.android.ui.onboarding.OnboardingScreen
import com.iris.android.ui.sensors.SensorBatchScreen
import com.iris.android.ui.sensors.SensorsScreen
import com.iris.android.ui.settings.SettingsScreen
import com.iris.android.ui.today.TodayScreen
import com.iris.android.ui.collector.CollectorScreen
import com.iris.android.ui.components.OrbVibe
import com.iris.android.ui.components.LocalOrbVibe
import com.iris.android.ui.more.MoreScreen
import com.iris.android.ui.review.ReviewScreen
import com.iris.android.ui.theme.LocalIrisColors

object Routes {
    const val CHAT = "chat?draft={draft}"
    const val TODAY = "today"
    const val JOURNAL = "journal?entry={entry}"
    const val JOURNAL_VOICE = "journal/voice"
    const val INSIGHTS = "insights"
    const val INSIGHT = "insights/{id}"
    const val MORE = "more"
    const val HABITS = "habits"
    const val NOTICED = "noticed"
    const val REVIEW = "review"
    const val IMPORT = "import?batch={batch}"
    const val SENSORS = "sensors"
    const val SENSOR_BATCH = "sensors/{id}"
    const val SETTINGS = "settings"
    const val COLLECTOR = "collector"
    const val ONBOARDING = "onboarding"
}

private data class Tab(val label: String, val route: String, val icon: Int, val selected: Int)

private val tabs = listOf(
    Tab("Chat", "chat", R.drawable.ic_chat, R.drawable.ic_chat_fill),
    Tab("Today", "today", R.drawable.ic_today, R.drawable.ic_today_fill),
    Tab("Journal", "journal", R.drawable.ic_edit_note, R.drawable.ic_edit_note_fill),
    Tab("Habits", "habits", R.drawable.ic_repeat, R.drawable.ic_repeat_fill),
    Tab("More", "more", R.drawable.ic_more_horiz, R.drawable.ic_more_horiz_fill),
)

@Composable
fun IrisNavHost(pendingDestination: String?, onDestinationHandled: () -> Unit) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route.orEmpty().substringBefore('?')
    val currentTab = when {
        route == "journal/voice" -> "journal"
        route.startsWith("insights/") -> "more"
        route in setOf("more", "insights", "noticed", "review", "import", "sensors", "sensors/{id}", "settings", "collector") -> "more"
        else -> route
    }
    val vibe = when {
        route in setOf("journal", "journal/voice", "habits") -> OrbVibe.High
        route.startsWith("insights") || route == "noticed" -> OrbVibe.Low
        route in setOf("review", "import") -> OrbVibe.Cool
        route.startsWith("sensors") || route == "settings" -> OrbVibe.Dim
        else -> OrbVibe.Calm
    }
    val colors = LocalIrisColors.current
    val link by IrisLink.state.collectAsState()
    LaunchedEffect(link) {
        if (link is LinkState.Ready) {
            val state = runCatching { IrisLink.api().send("GET", "/onboarding/state", null, OnboardingState.serializer()) }.getOrNull()
            if (state != null && state.step != "done") {
                nav.navigate("onboarding") { popUpTo(nav.graph.id) { inclusive = true }; launchSingleTop = true }
            }
        }
    }
    LaunchedEffect(pendingDestination) {
        if (pendingDestination == "collector") {
            nav.navigate("collector") { launchSingleTop = true }
            onDestinationHandled()
        }
    }
    val openCollector: () -> Unit = { nav.navigate("collector") }
    val gated: @Composable (@Composable () -> Unit) -> Unit = { content ->
        Gated(onOpenCollector = openCollector) {
            content()
        }
    }
    CompositionLocalProvider(LocalOrbVibe provides vibe) {
        Scaffold(bottomBar = {
            if (route !in setOf("onboarding", "journal/voice", "insights/{id}", "sensors/{id}") && !WindowInsets.isImeVisible) {
                NavigationBar(containerColor = colors.bg1) {
                    tabs.forEach { tab ->
                        val selected = currentTab == tab.route
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                nav.navigate(tab.route) {
                                    popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(painterResource(if (selected) tab.selected else tab.icon), contentDescription = tab.label) },
                            label = { Text(tab.label) }, alwaysShowLabel = true,
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = colors.ink, selectedTextColor = colors.ink,
                                unselectedIconColor = colors.ink3, unselectedTextColor = colors.ink3,
                                indicatorColor = colors.bg3,
                            ),
                        )
                    }
                }
            }
        }, containerColor = colors.bg0) { padding ->
            // Destinations own their scaffold padding; the bottom bar is inset once here.
            androidx.compose.foundation.layout.Box(
                androidx.compose.ui.Modifier.padding(bottom = padding.calculateBottomPadding())) {
                NavHost(navController = nav, startDestination = Routes.CHAT) {
                    composable(Routes.CHAT, arguments = listOf(navArgument("draft") { nullable = true; defaultValue = null })) {
                        gated { ChatScreen(it.arguments?.getString("draft")) }
                    }
                    composable(Routes.TODAY) { gated { TodayScreen(nav::navigate) } }
                    composable(Routes.JOURNAL, arguments = listOf(navArgument("entry") { nullable = true; defaultValue = null })) {
                        gated { JournalScreen(it.arguments?.getString("entry"), nav::navigate) }
                    }
                    composable(Routes.JOURNAL_VOICE) {
                        gated {
                            JournalVoiceScreen(
                                onBack = { nav.popBackStack() },
                                onReview = { batchId ->
                                    nav.navigate("import?batch=$batchId") {
                                        popUpTo(Routes.JOURNAL_VOICE) { inclusive = true }
                                    }
                                },
                            )
                        }
                    }
                    composable(Routes.INSIGHTS) { gated { InsightsScreen(nav::navigate) } }
                    composable(Routes.INSIGHT, arguments = listOf(navArgument("id") { type = NavType.StringType })) {
                        gated {
                            InsightDetailScreen(
                                requireNotNull(it.arguments?.getString("id")),
                                nav::navigate,
                                onBack = { nav.popBackStack() },
                                onDecisionDone = {
                                    nav.navigate(Routes.INSIGHTS) {
                                        popUpTo(nav.graph.findStartDestination().id)
                                        launchSingleTop = true
                                    }
                                },
                            )
                        }
                    }
                    composable(Routes.MORE) { gated { MoreScreen(nav::navigate) } }
                    composable(Routes.HABITS) { gated { HabitsScreen() } }
                    composable(Routes.NOTICED) { gated { NoticedScreen(nav::navigate) } }
                    composable(Routes.REVIEW) { gated { ReviewScreen() } }
                    composable(Routes.IMPORT, arguments = listOf(navArgument("batch") { nullable = true; defaultValue = null })) {
                        gated { ImportScreen(it.arguments?.getString("batch")) }
                    }
                    composable(Routes.SENSORS) { gated { SensorsScreen(nav::navigate) } }
                    composable(Routes.SENSOR_BATCH, arguments = listOf(navArgument("id") { type = NavType.StringType })) {
                        gated {
                            SensorBatchScreen(requireNotNull(it.arguments?.getString("id")).toLong()) {
                                nav.popBackStack()
                            }
                        }
                    }
                    composable(Routes.SETTINGS) { gated { SettingsScreen(nav::navigate) } }
                    composable(Routes.COLLECTOR) { CollectorScreen { nav.popBackStack() } }
                    composable(Routes.ONBOARDING) {
                        gated {
                            OnboardingScreen {
                                nav.navigate("chat") { popUpTo("onboarding") { inclusive = true } }
                            }
                        }
                    }
                }
            }
        }
    }
}
