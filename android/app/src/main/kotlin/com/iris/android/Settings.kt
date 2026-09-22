package com.iris.android

import android.content.Context

/**
 * Where the app stores the laptop's LAN URL and the bearer token.
 *
 * The Keystore-backed secure storage is the production path; this
 * SharedPreferences fallback is what runs until the UI branch lands
 * the Keystore wrapper. The token is still app-private, just not
 * hardware-backed. The owner can rotate the bearer from IRIS settings.
 */
object Settings {
    private const val PREFS = "iris_settings"
    private const val KEY_BASE_URL = "laptop_base_url"
    private const val KEY_BEARER = "bearer_token"

    fun laptopBaseUrl(ctx: Context): String {
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_BASE_URL, "http://127.0.0.1:8765/")
            ?: "http://127.0.0.1:8765/"
    }

    fun bearer(ctx: Context): String {
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_BEARER, "") ?: ""
    }

    fun save(ctx: Context, baseUrl: String, bearer: String) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_BASE_URL, baseUrl)
            .putString(KEY_BEARER, bearer)
            .apply()
    }
}
