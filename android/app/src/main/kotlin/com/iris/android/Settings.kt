package com.iris.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.net.URI
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONException
import org.json.JSONObject

/** Connection details accepted only through pairing QR or explicit manual entry. */
object Settings {
    private const val PREFS = "iris_settings"
    private const val KEY_BASE_URL = "laptop_base_url"
    private const val KEY_BEARER = "bearer_token"
    private const val KEY_PUBLIC_KEY_SHA256 = "public_key_sha256"
    private const val KEY_COLLECTING = "collection_enabled"
    private const val KEY_COLLECTION_START = "collection_started_at"
    private const val KEY_COLLECTION_BOOT = "collection_boot_count"
    private const val KEY_ALIAS = "iris_mobile_bearer"
    private const val IV_BYTES = 12

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private fun bootCount(ctx: Context) = android.provider.Settings.Global.getInt(
        ctx.contentResolver, android.provider.Settings.Global.BOOT_COUNT, -1)

    fun laptopBaseUrl(ctx: Context): String = prefs(ctx).getString(KEY_BASE_URL, "") ?: ""
    fun laptopHost(ctx: Context): String? = runCatching { URI(laptopBaseUrl(ctx)).host }.getOrNull()
    fun publicKeySha256(ctx: Context): String = prefs(ctx).getString(KEY_PUBLIC_KEY_SHA256, "") ?: ""
    fun hasBearer(ctx: Context): Boolean = !prefs(ctx).getString(KEY_BEARER, null).isNullOrBlank()
    fun collectionRequested(ctx: Context): Boolean = prefs(ctx).getBoolean(KEY_COLLECTING, false)

    /** A reboot requires an explicit tap to resume location collection. */
    fun collectionEnabled(ctx: Context): Boolean = collectionRequested(ctx) &&
        prefs(ctx).getInt(KEY_COLLECTION_BOOT, -2) == bootCount(ctx)

    fun collectionStartedAt(ctx: Context): Long = prefs(ctx).getLong(KEY_COLLECTION_START, 0)

    fun setCollectionEnabled(ctx: Context, enabled: Boolean) {
        val change = prefs(ctx).edit().putBoolean(KEY_COLLECTING, enabled)
        if (enabled) {
            if (!collectionEnabled(ctx)) change.putLong(KEY_COLLECTION_START, System.currentTimeMillis())
            change.putInt(KEY_COLLECTION_BOOT, bootCount(ctx))
        }
        check(change.commit()) { "Could not save collection setting" }
    }

    fun bearer(ctx: Context): String {
        val saved = prefs(ctx).getString(KEY_BEARER, null) ?: return ""
        try {
            val encrypted = Base64.decode(saved, Base64.NO_WRAP)
            require(encrypted.size > IV_BYTES)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, secretKey(),
                GCMParameterSpec(128, encrypted.copyOfRange(0, IV_BYTES)))
            return cipher.doFinal(encrypted.copyOfRange(IV_BYTES, encrypted.size))
                .toString(Charsets.UTF_8)
        } catch (e: Exception) {
            throw IllegalStateException("Stored pairing token is unreadable; pair this phone again", e)
        }
    }

    fun save(ctx: Context, baseUrl: String, bearer: String?, publicKeySha256: String) {
        val url = URI(baseUrl.trim())
        require(url.scheme == "https" && url.host != null && url.port in 1..65535 &&
                url.userInfo == null && url.query == null && url.fragment == null &&
                (url.path.isNullOrEmpty() || url.path == "/")) {
            "Use the HTTPS LAN address shown in IRIS Settings"
        }
        val token = bearer?.trim().takeUnless { it.isNullOrBlank() }
        if (token == null && !hasBearer(ctx)) {
            throw IllegalArgumentException(
                "Scan the pairing QR shown right after generating a token in IRIS Settings")
        }
        if (token != null) require(token.matches(Regex("[0-9a-f]{64}"))) {
            "Pairing token must be 64 lowercase hex digits"
        }
        val pin = publicKeySha256.trim().lowercase()
        require(pin.matches(Regex("[0-9a-f]{64}"))) {
            "Server key SHA-256 must be 64 hex digits"
        }

        val edit = prefs(ctx).edit()
            .putString(KEY_BASE_URL, url.toString().trimEnd('/') + "/")
            .putString(KEY_PUBLIC_KEY_SHA256, pin)
        if (token != null) {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, secretKey())
            val sealed = cipher.iv + cipher.doFinal(token.toByteArray(Charsets.UTF_8))
            edit.putString(KEY_BEARER, Base64.encodeToString(sealed, Base64.NO_WRAP))
        }
        check(edit.commit()) { "Could not save pairing details" }
    }

    data class PairingCode(val url: String, val key: String, val token: String?)

    internal fun parsePairingCode(raw: String): PairingCode {
        val json = try { JSONObject(raw) } catch (_: JSONException) {
            throw IllegalArgumentException("This QR code is not an IRIS pairing code")
        }
        if (json.optInt("iris", -1) != 1) {
            throw IllegalArgumentException("This QR code is not an IRIS pairing code")
        }
        val url = json.optString("url").trim()
        val key = json.optString("key").trim()
        if (url.isEmpty() || key.isEmpty()) {
            throw IllegalArgumentException("The IRIS pairing code is incomplete")
        }
        return PairingCode(url, key, json.optString("token").trim().ifEmpty { null })
    }

    fun applyPairingCode(ctx: Context, raw: String): PairingCode {
        val code = parsePairingCode(raw)
        save(ctx, code.url, code.token, code.key)
        return code
    }

    private fun secretKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(
            KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build())
        return generator.generateKey()
    }
}
