package com.iris.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Text

/**
 * Single-screen placeholder; the real UI surface lands on a separate
 * branch (Phase 4 of the original plan). What this activity proves is
 * that the project compiles and the bearer-protected auth handshake
 * works against IRIS over the LAN bind.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { Text("IRIS — placeholder") }
    }
}
