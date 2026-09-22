"""DB-backed tests for SensorService.

The conftest autouse fixture truncates every public table before each
test, so these tests start with an empty database.
"""
import unittest

from agent.database import db
from agent.sensors.service import SensorService


def _truncate_sensor_tables() -> None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE sensor_observations, sensor_batches RESTART IDENTITY CASCADE;")
        conn.commit()


class SensorServiceTests(unittest.TestCase):
    def setUp(self):
        _truncate_sensor_tables()
        self.service = SensorService()

    def test_confirmed_batch_writes_sensor_observations(self):
        batch = {
            "source": "pixel",
            "observations": [
                {"source_type": "pixel_steps", "occurred_at": "2026-09-22T10:00:00Z",
                 "value_num": 1200, "payload_hash": "h1"},
                {"source_type": "pixel_app_usage", "occurred_at": "2026-09-22T10:05:00Z",
                 "value_text": "com.android.chrome", "payload_hash": "h2"},
            ],
        }
        batch_id = self.service.stage_batch(batch, payload_path="/tmp/x.json")
        ids = self.service.commit_batch(batch_id, batch["observations"])
        self.assertEqual(len(ids), 2)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM sensor_observations")
            self.assertEqual(cur.fetchone()[0], 2)

    def test_create_sensor_observation_raises_for_unconfirmed(self):
        batch_id = self.service.stage_batch(
            {"source": "pixel", "observations": []}, payload_path="/tmp/x.json")
        with self.assertRaises(ValueError):
            self.service.create_sensor_observation(batch_id)


class ServiceSeamTests(unittest.TestCase):
    """Tests that need the agent.sensors package to resolve relative imports."""

    def test_service_class_exposes_the_seam_methods(self):
        from agent.sensors.service import SensorService
        for method in ("stage_batch", "confirm_batch",
                       "create_sensor_observation", "commit_batch"):
            with self.subTest(method=method):
                self.assertTrue(hasattr(SensorService, method))


class SensorServiceIdempotencyTests(unittest.TestCase):
    """Separate from ServiceSeamTests so setUp() runs."""

    def setUp(self):
        _truncate_sensor_tables()
        self.service = SensorService()

    def test_confirm_a_second_time_is_a_noop(self):
        batch_id = self.service.stage_batch(
            {"source": "pixel", "observations": []}, payload_path="/tmp/x.json")
        self.service.confirm_batch(batch_id)
        self.service.confirm_batch(batch_id)  # idempotent
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM sensor_batches WHERE id = %s",
                        (batch_id,))
            self.assertEqual(cur.fetchone()[0], "confirmed")


if __name__ == "__main__":
    unittest.main()
