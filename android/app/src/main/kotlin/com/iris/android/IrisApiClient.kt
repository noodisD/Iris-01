package com.iris.android

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/**
 * The phone's only HTTP client to IRIS.
 *
 * Every mobile route — pairing, sensor intake, the future UI surfaces —
 * goes through this class. The bearer is supplied at construction; the
 * token is stored in the Android Keystore (a follow-up adds the
 * wrapping; the token storage is the next step on the UI branch).
 *
 * Stateless, thread-safe, no caching. The caller decides retry policy.
 */
class IrisApiClient(
    private val baseUrl: String,
    private val bearer: String,
    private val http: OkHttpClient = OkHttpClient(),
) {
    /** Pair the app to IRIS. Returns true on a 2xx response. */
    fun pair(token: String, lanBindEnabled: Boolean): Boolean {
        val body = JSONObject().apply {
            put("token", token)
            put("lan_bind_enabled", lanBindEnabled)
        }.toString().toRequestBody(JSON)
        val req = Request.Builder()
            .url("${baseUrl}api/mobile/pair")
            .header("Authorization", "Bearer $bearer")
            .post(body)
            .build()
        http.newCall(req).execute().use { return it.isSuccessful }
    }

    /** Push a sensor batch. Returns the new batch id. */
    fun pushSensorBatch(payload: Map<String, Any?>): Long {
        val body = JSONObject(payload).toString().toRequestBody(JSON)
        val req = Request.Builder()
            .url("${baseUrl}api/mobile/sensor/intake")
            .header("Authorization", "Bearer $bearer")
            .post(body)
            .build()
        http.newCall(req).execute().use {
            if (!it.isSuccessful) error("intake failed: ${it.code}")
            val json = JSONObject(it.body!!.string())
            return json.getLong("batch_id")
        }
    }

    companion object {
        private val JSON = "application/json".toMediaType()
    }
}
