"""Pure-module tests for the sensor seam — modules that don't need
to import from elsewhere in agent/.

Modules that need the agent package (repository.py imports
agent.database, service.py imports .repository) are tested in
test_sensor_service.py.
"""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENSORS_DIR = ROOT / "agent" / "sensors"


def _load_sensors_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SENSORS_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TransportShapeTests(unittest.TestCase):
    def test_transport_is_an_abstract_base(self):
        transport = _load_sensors_module("transport")
        # LocalExportTransport must subclass SyncTransport and implement fetch.
        self.assertTrue(hasattr(transport, "SyncTransport"))
        self.assertTrue(hasattr(transport, "LocalExportTransport"))
        self.assertTrue(
            issubclass(transport.LocalExportTransport, transport.SyncTransport))
        # A bare SyncTransport cannot be instantiated.
        with self.assertRaises(TypeError):
            transport.SyncTransport()


class LocalExportTransportTests(unittest.TestCase):
    def test_picks_up_files_in_arrival_order(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.json").write_text("{}")
            (root / "b.json").write_text("{}")
            transport = _load_sensors_module("transport").LocalExportTransport(root)
            paths = transport.fetch()
            self.assertEqual([p.name for p in paths], ["a.json", "b.json"])

    def test_empty_staging_returns_empty_list(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            transport = _load_sensors_module("transport").LocalExportTransport(Path(d))
            self.assertEqual(transport.fetch(), [])


class HttpIntakeTransportTests(unittest.TestCase):
    def test_push_posts_payload_with_bearer(self):
        transport = _load_sensors_module("transport").HttpIntakeTransport(
            intake_url="http://127.0.0.1:8000/api/mobile/sensor/intake",
            bearer_token="the-token")
        seen = {}
        from contextlib import contextmanager
        @contextmanager
        def fake_urlopen(req):
            seen["url"] = req.full_url
            seen["method"] = req.method
            seen["headers"] = dict(req.headers)
            seen["body"] = req.data.decode()
            class Resp:
                def __enter__(self_inner):
                    return self_inner
                def __exit__(self_inner, *a):
                    return False
                def read(self_inner):
                    return b'{"batch_id": 7, "observation_count": 5}'
            yield Resp()
        import unittest.mock as mock
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            response = transport.push({"device": "Pixel 10a", "tiers": {}})
        self.assertEqual(response["batch_id"], 7)
        self.assertEqual(seen["url"], "http://127.0.0.1:8000/api/mobile/sensor/intake")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer the-token")
        self.assertIn('"device": "Pixel 10a"', seen["body"])

    def test_fetch_raises_with_helpful_message(self):
        transport = _load_sensors_module("transport").HttpIntakeTransport(
            intake_url="http://x", bearer_token="y")
        with self.assertRaises(NotImplementedError) as cm:
            transport.fetch()
        self.assertIn("push", str(cm.exception).lower())


class EvidenceWeightsTests(unittest.TestCase):
    """Sensor evidence must be named in EVIDENCE_WEIGHTS.

    ADR-0017: a phone reading is signal, not deliberate logging. The
    engines treat it as supplementary. The named entries are the
    contract; a missing entry falls through to 0.5 (the bare habit-tick
    default) which would silently inflate the weight of a sensor reading.
    """

    SOURCES = (
        "pixel_location", "pixel_app_usage", "pixel_steps",
        "fitbit_heart_rate", "fitbit_sleep", "fitbit_spo2",
    )

    def _constants(self):
        spec = importlib.util.spec_from_file_location(
            "constants", ROOT / "agent" / "constants.py")
        if spec is None or spec.loader is None:
            raise ImportError("could not load constants")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_sensor_source_appears(self):
        constants = self._constants()
        for source in self.SOURCES:
            self.assertIn(source, constants.EVIDENCE_WEIGHTS)

    def test_weights_are_in_open_unit_interval(self):
        constants = self._constants()
        for source in self.SOURCES:
            weight = constants.EVIDENCE_WEIGHTS[source]
            self.assertGreater(weight, 0.0)
            self.assertLessEqual(weight, 1.0)

    def test_max_sensor_occurrences_constant_exists(self):
        constants = self._constants()
        self.assertTrue(hasattr(constants, "MAX_SENSOR_OCCURRENCES_PER_DAY_PER_THEME"))
        self.assertGreater(constants.MAX_SENSOR_OCCURRENCES_PER_DAY_PER_THEME, 0)


class PixelAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = _load_sensors_module("adapters").PixelAdapter()
        self.fixture = ROOT / "tests" / "fixtures" / "pixel_export_minimal.json"

    def test_parses_three_tiers(self):
        batch = self.adapter.parse(self.fixture)
        self.assertEqual(batch["source"], "pixel")
        obs = batch["observations"]
        # 2 location + 2 app_usage + 1 steps = 5
        self.assertEqual(len(obs), 5)
        types = sorted({o["source_type"] for o in obs})
        self.assertEqual(types, ["pixel_app_usage", "pixel_location", "pixel_steps"])

    def test_each_observation_has_payload_hash(self):
        batch = self.adapter.parse(self.fixture)
        for obs in batch["observations"]:
            self.assertIn("payload_hash", obs)
            self.assertEqual(len(obs["payload_hash"]), 16)

    def test_missing_date_drops_the_observation(self):
        # ADR-0013: a date is read or absent; unparseable readings are
        # dropped at parse time, not committed with a guessed date.
        import json
        import tempfile
        bad = {"device": "Pixel 10a", "tiers": {"location": [
            {"ts": None, "lat": 0, "lon": 0}]}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(bad, f)
            path = f.name
        try:
            batch = self.adapter.parse(path)
        finally:
            Path(path).unlink()
        self.assertEqual(batch["observations"], [])
        self.assertEqual(batch["dropped_count"], 1)

    def test_batch_includes_raw_payload_hash(self):
        batch = self.adapter.parse(self.fixture)
        self.assertIn("raw_payload_hash", batch)
        self.assertEqual(len(batch["raw_payload_hash"]), 64)


class FitbitAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = _load_sensors_module("adapters").FitbitAdapter()
        self.fixture = ROOT / "tests" / "fixtures" / "fitbit_export_minimal.json"

    def test_parses_three_tiers(self):
        batch = self.adapter.parse(self.fixture)
        self.assertEqual(batch["source"], "fitbit")
        types = sorted({o["source_type"] for o in batch["observations"]})
        self.assertEqual(types,
                         ["fitbit_heart_rate", "fitbit_sleep", "fitbit_spo2"])

    def test_count_matches_fixture(self):
        # 2 heart_rate + 1 sleep + 1 spo2 = 4
        batch = self.adapter.parse(self.fixture)
        self.assertEqual(len(batch["observations"]), 4)

    def test_seam_is_honest_pixel_and_fitbit_share_shape(self):
        # The proof that the seam is honest: the two adapters produce
        # batches of the same shape. If this fails, the seam is wrong.
        adapters = _load_sensors_module("adapters")
        pixel_batch = adapters.PixelAdapter().parse(
            ROOT / "tests" / "fixtures" / "pixel_export_minimal.json")
        fitbit_batch = adapters.FitbitAdapter().parse(
            ROOT / "tests" / "fixtures" / "fitbit_export_minimal.json")
        self.assertEqual(set(pixel_batch), set(fitbit_batch))
        for key in ("source", "observations", "dropped_count",
                    "raw_payload_hash"):
            self.assertIn(key, pixel_batch)
            self.assertIn(key, fitbit_batch)


class DetectTests(unittest.TestCase):
    def test_detect_picks_pixel(self):
        adapters = _load_sensors_module("adapters")
        self.assertEqual(
            adapters.detect(
                ROOT / "tests" / "fixtures" / "pixel_export_minimal.json"),
            "pixel")

    def test_detect_picks_fitbit(self):
        adapters = _load_sensors_module("adapters")
        self.assertEqual(
            adapters.detect(
                ROOT / "tests" / "fixtures" / "fitbit_export_minimal.json"),
            "fitbit")


if __name__ == "__main__":
    unittest.main()
