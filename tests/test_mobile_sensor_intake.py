"""The /api/mobile/sensor/intake route — phone pushes the JSON file
the PixelAdapter would parse, IRIS stages it as a batch.

The route does NOT auto-confirm: the owner reviews before commit, the
same as the manual-export path (ADR-0017).
"""
import json
import unittest


class IntakeRouteTests(unittest.TestCase):
    def setUp(self):
        from agent.database import db
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE sensor_observations, sensor_batches "
                        "RESTART IDENTITY CASCADE;")
            conn.commit()

    def test_intake_returns_batch_id_for_pixel(self):
        from fastapi.testclient import TestClient
        from iris_api import app
        with TestClient(app) as client:
            payload = json.loads(open(
                "tests/fixtures/pixel_export_minimal.json").read())
            r = client.post("/api/mobile/sensor/intake", json=payload)
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertIn("batch_id", body)
            self.assertGreater(body["batch_id"], 0)
            self.assertEqual(body["observation_count"], 5)
            self.assertEqual(body["dropped_count"], 0)

    def test_intake_rejects_payload_with_no_device(self):
        from fastapi.testclient import TestClient
        from iris_api import app
        with TestClient(app) as client:
            r = client.post("/api/mobile/sensor/intake",
                            json={"tiers": {}})
            self.assertEqual(r.status_code, 400)

    def test_intake_rejects_unknown_device(self):
        from fastapi.testclient import TestClient
        from iris_api import app
        with TestClient(app) as client:
            r = client.post("/api/mobile/sensor/intake",
                            json={"device": "MysteryGadget",
                                  "tiers": {"steps": []}})
            self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
