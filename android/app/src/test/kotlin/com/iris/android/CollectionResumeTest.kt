package com.iris.android

import org.junit.Assert.assertEquals
import org.junit.Test

class CollectionResumeTest {
    @Test fun resumesByItselfOnlyWhenLocationIsAllowedAllTheTime() {
        assertEquals(ResumeAction.RESUME, resumeAction(requested = true, backgroundLocation = true))
        assertEquals(ResumeAction.ASK, resumeAction(requested = true, backgroundLocation = false))
    }

    @Test fun neverStartsCollectionTheOwnerDidNotAskFor() {
        assertEquals(ResumeAction.NOTHING, resumeAction(requested = false, backgroundLocation = true))
        assertEquals(ResumeAction.NOTHING, resumeAction(requested = false, backgroundLocation = false))
    }
}
