package com.iris.android.api

import okhttp3.MediaType
import okhttp3.RequestBody
import okio.Buffer
import okio.BufferedSink
import okio.ForwardingSink
import okio.buffer

/** Counts bytes actually written, including multipart boundaries; unknown lengths are indeterminate. */
internal class CountingRequestBody(
    private val delegate: RequestBody,
    private val onProgress: (Float) -> Unit,
) : RequestBody() {
    override fun contentType(): MediaType? = delegate.contentType()
    override fun contentLength(): Long = delegate.contentLength()

    override fun writeTo(sink: BufferedSink) {
        val length = contentLength()
        var written = 0L
        val counting = object : ForwardingSink(sink) {
            override fun write(source: Buffer, byteCount: Long) {
                super.write(source, byteCount)
                written += byteCount
                if (length > 0L) onProgress((written.toDouble() / length).toFloat().coerceIn(0f, 1f))
            }
        }.buffer()
        delegate.writeTo(counting)
        counting.flush()
    }
}
