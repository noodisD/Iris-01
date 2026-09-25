package com.iris.android.api

internal fun describeRefusal(code: Int, detail: String, root: String): String? = when {
    code == 401 -> "IRIS no longer accepts this phone's token. Generate a pairing token in IRIS Settings and scan it."
    code == 403 && detail == "lan bind disabled" -> "Phone access is switched off in IRIS. Pair again from IRIS Settings."
    code == 403 -> "IRIS refused the connection (403: $detail)"
    code == 503 -> "No phone is paired in IRIS. Pair again from IRIS Settings."
    code == 404 -> "No IRIS phone listener at $root. Scan the address QR in IRIS Settings."
    else -> null
}

fun pinMismatchMessage(root: String): String =
    "The laptop at $root is not the paired IRIS (server key or address mismatch). Scan the pairing QR again."
