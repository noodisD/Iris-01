package com.iris.android

import com.iris.android.api.shouldReplaceLink
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LinkRefreshTest {
    @Test fun sameReadyConnectionIsKept() {
        assertFalse(shouldReplaceLink(true, true, true))
    }

    @Test fun changedConnectionOrReadinessReplaces() {
        assertTrue(shouldReplaceLink(true, true, false))
        assertTrue(shouldReplaceLink(false, true, true))
        assertTrue(shouldReplaceLink(true, false, true))
    }
}
