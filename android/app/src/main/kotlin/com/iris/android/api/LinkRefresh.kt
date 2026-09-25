package com.iris.android.api

internal fun shouldReplaceLink(currentIsReady: Boolean, nextIsReady: Boolean, sameConnection: Boolean): Boolean =
    !(currentIsReady && nextIsReady && sameConnection)
