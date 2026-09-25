package com.iris.android

import com.iris.android.lock.AppLockPolicy
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AppLockPolicyTest {
    @Test fun locksOnNewProcessAndAtExactFiveMinuteBoundary() {
        val policy = AppLockPolicy(300_000)
        assertTrue(policy.onForeground(0))
        policy.onUnlocked()
        assertFalse(policy.onForeground(1))
        policy.onBackground(10_000)
        assertFalse(policy.onForeground(309_999))
        policy.onBackground(400_000)
        assertTrue(policy.onForeground(700_000))
        assertTrue(policy.onForeground(700_001))
        policy.onUnlocked()
        assertFalse(policy.onForeground(700_002))
    }

    @Test fun backgroundingWhileLockedDoesNotUnlock() {
        val policy = AppLockPolicy(300_000)
        policy.onBackground(50)
        assertTrue(policy.onForeground(100))
    }
}
