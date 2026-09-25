package com.iris.android

import com.iris.android.api.apiError
import org.junit.Assert.assertEquals
import org.junit.Test

class IrisApiErrorTest {
    private val root = "https://192.168.1.30:8765"

    @Test fun pairs401RefusalWithExistingCollectorRemedy() {
        val error = apiError(401, """{"detail":"invalid bearer"}""", "fallback", root)
        assertEquals("http_401", error.code)
        assertEquals("IRIS no longer accepts this phone's token. Generate a pairing token in IRIS Settings and scan it.",
            error.message)
    }

    @Test fun validationAndMessageTakeCorrectPrecedence() {
        assertEquals("field required", apiError(422, """{"detail":[{"msg":"field required"}]}""", "fallback", root).message)
        val explicit = apiError(400, """{"code":"bad_input","message":"m","detail":"d"}""", "fallback", root)
        assertEquals("bad_input", explicit.code)
        assertEquals("m", explicit.message)
    }

    @Test fun nonJsonResponseUsesReasonPhrase() {
        val error = apiError(500, "<html>error</html>", "Internal Server Error", root)
        assertEquals("http_500", error.code)
        assertEquals("Internal Server Error", error.message)
    }
}
