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



class LanHostRuleTests(unittest.TestCase):
    """Which addresses the phone listener may bind (ADR-0018, ADR-0022)."""

    def test_home_and_private_network_addresses_are_accepted(self):
        from agent.config import Settings
        for host in ("192.168.1.30", "10.0.0.5", "172.16.4.2", "100.109.145.71", "100.64.0.1"):
            self.assertEqual(Settings.validate_lan_host(host), host)

    def test_public_and_unusual_addresses_are_refused(self):
        from agent.config import Settings
        # 100.63.x and 100.128.x sit just outside the private-network range.
        for host in ("8.8.8.8", "100.63.255.255", "100.128.0.1", "0.0.0.0", "::1", "not-an-ip"):
            with self.assertRaises(ValueError, msg=host):
                Settings.validate_lan_host(host)


if __name__ == "__main__":
    unittest.main()
