package com.iris.android.api

internal class SseParser {
    private val data = StringBuilder()

    fun feed(line: String): String? {
        if (line.isEmpty()) {
            if (data.isEmpty()) return null
            val block = data.toString()
            data.setLength(0)
            return block
        }
        if (line.startsWith("data:")) data.append(line.substring(5).trim())
        return null
    }
}
