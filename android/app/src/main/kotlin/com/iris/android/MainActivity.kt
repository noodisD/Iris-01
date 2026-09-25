package com.iris.android

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.runtime.mutableStateOf
import androidx.fragment.app.FragmentActivity
import com.iris.android.lock.AppLock
import com.iris.android.ui.IrisRoot
import com.iris.android.ui.theme.IrisTheme

/** The collector is independent of this private, device-authenticated UI. */
class MainActivity : FragmentActivity() {
    companion object {
        const val EXTRA_DESTINATION = "com.iris.android.extra.DESTINATION"
        const val DESTINATION_COLLECTOR = "collector"
    }

    private val locked = mutableStateOf(true)
    private val lockMessage = mutableStateOf<String?>(null)
    private val lockNeedsSetup = mutableStateOf(false)
    private val pendingDestination = mutableStateOf<String?>(null)
    private var autoPrompt = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (Build.VERSION.SDK_INT >= 33) setRecentsScreenshotEnabled(false)
        pendingDestination.value = intent?.getStringExtra(EXTRA_DESTINATION)
        setContent {
            IrisTheme {
                IrisRoot(
                    locked = locked.value,
                    lockMessage = lockMessage.value,
                    lockNeedsSetup = lockNeedsSetup.value,
                    onUnlock = ::authenticate,
                    pendingDestination = pendingDestination.value,
                    onDestinationHandled = { pendingDestination.value = null },
                )
            }
        }
    }

    override fun onStart() {
        super.onStart()
        locked.value = AppLock.onForeground(SystemClock.elapsedRealtime())
        if (locked.value) autoPrompt = true
    }

    override fun onResume() {
        super.onResume()
        if (locked.value && autoPrompt) {
            autoPrompt = false
            authenticate()
        }
    }

    override fun onStop() {
        if (!isChangingConfigurations) AppLock.onBackground(SystemClock.elapsedRealtime())
        super.onStop()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        pendingDestination.value = intent.getStringExtra(EXTRA_DESTINATION)
    }

    private fun authenticate() {
        val authenticators = BiometricManager.Authenticators.BIOMETRIC_WEAK or
            BiometricManager.Authenticators.DEVICE_CREDENTIAL
        if (BiometricManager.from(this).canAuthenticate(authenticators) != BiometricManager.BIOMETRIC_SUCCESS) {
            lockNeedsSetup.value = true
            lockMessage.value = "Set a screen lock (PIN, pattern, password or fingerprint) in Android Settings to open IRIS."
            return
        }
        lockNeedsSetup.value = false
        BiometricPrompt(this, mainExecutor, object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                AppLock.onUnlocked()
                locked.value = false
                lockMessage.value = null
                lockNeedsSetup.value = false
            }

            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                if (errorCode !in setOf(
                        BiometricPrompt.ERROR_USER_CANCELED,
                        BiometricPrompt.ERROR_CANCELED,
                        BiometricPrompt.ERROR_NEGATIVE_BUTTON,
                    )) lockMessage.value = errString.toString()
            }
        }).authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("Unlock IRIS")
                .setSubtitle("Your journal and conversations stay private")
                .setAllowedAuthenticators(authenticators)
                .build(),
        )
    }
}
