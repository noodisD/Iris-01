@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.iris.android.ui.components

import androidx.compose.foundation.layout.Box
import androidx.compose.material3.pulltorefresh.PullToRefreshContainer
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll

@Composable
fun RefreshableList(refreshing: Boolean, onRefresh: () -> Unit, content: @Composable () -> Unit) {
    val state = rememberPullToRefreshState()
    if (state.isRefreshing) LaunchedEffect(Unit) { onRefresh() }
    LaunchedEffect(refreshing) { if (!refreshing) state.endRefresh() }
    Box(Modifier.nestedScroll(state.nestedScrollConnection)) {
        content()
        PullToRefreshContainer(state, Modifier.align(Alignment.TopCenter))
    }
}
