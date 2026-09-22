"""LAN-bind settings — the loopback invariant narrows deliberately.

ADR-0018: the LAN bind is OFF by default. A fresh IRIS install must
not suddenly open a port on the home Wi-Fi.
"""
import unittest


class MobileConfigTests(unittest.TestCase):
    def test_lan_bind_host_is_a_string(self):
        from agent.config import settings
        self.assertIsInstance(settings.LAN_BIND_HOST, str)

    def test_lan_bind_port_is_in_unprivileged_range(self):
        from agent.config import settings
        self.assertIsInstance(settings.LAN_BIND_PORT, int)
        self.assertGreaterEqual(settings.LAN_BIND_PORT, 1024)
        self.assertLessEqual(settings.LAN_BIND_PORT, 65535)

    def test_default_lan_bind_is_disabled(self):
        from agent.config import settings
        self.assertFalse(settings.LAN_BIND_ENABLED)

    def test_mobile_bearer_hash_defaults_to_none(self):
        from agent.config import settings
        self.assertIsNone(settings.MOBILE_BEARER_HASH)


if __name__ == "__main__":
    unittest.main()
