@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.iris.android.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.RowScope
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.sp
import com.iris.android.R
import com.iris.android.ui.theme.LocalIrisColors
import com.iris.android.ui.theme.Serif

@Composable
fun IrisScaffold(
    title: AnnotatedString, kicker: String? = null,
    actions: @Composable RowScope.() -> Unit = {}, onBack: (() -> Unit)? = null,
    snackbarHostState: SnackbarHostState? = null,
    floatingActionButton: @Composable () -> Unit = {},
    content: @Composable (PaddingValues) -> Unit,
) {
    val colors = LocalIrisColors.current
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = {
            LargeTopAppBar(
                title = {
                    Column {
                        if (kicker != null) Kicker(kicker, Modifier.alpha(1f - scroll.state.collapsedFraction))
                        Text(title, fontFamily = Serif, fontSize = 28.sp, color = colors.ink)
                    }
                },
                navigationIcon = {
                    if (onBack != null) IconButton(onClick = onBack) {
                        Icon(painterResource(R.drawable.ic_arrow_back), contentDescription = "Back")
                    }
                },
                actions = actions, scrollBehavior = scroll,
                colors = TopAppBarDefaults.largeTopAppBarColors(
                    containerColor = colors.bg0, scrolledContainerColor = colors.bg1),
            )
        },
        snackbarHost = { if (snackbarHostState != null) SnackbarHost(snackbarHostState) },
        floatingActionButton = floatingActionButton,
        containerColor = colors.bg0, content = content,
    )
}

@Composable
fun IrisScaffold(
    title: String, kicker: String? = null,
    actions: @Composable RowScope.() -> Unit = {}, onBack: (() -> Unit)? = null,
    snackbarHostState: SnackbarHostState? = null,
    floatingActionButton: @Composable () -> Unit = {},
    content: @Composable (PaddingValues) -> Unit,
) = IrisScaffold(AnnotatedString(title), kicker, actions, onBack, snackbarHostState, floatingActionButton, content)
