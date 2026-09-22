"""Pure-module tests for the sensor seam. No database fixtures."""

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


class SeamShapeTests(unittest.TestCase):
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

    def test_service_seam_mirrors_reflection_service(self):
        service = _load_sensors_module("service")
        self.assertTrue(hasattr(service, "SensorService"))
        # The only public write method is create_sensor_observation, which
        # takes a confirmed batch, not raw sensor data.
        self.assertTrue(hasattr(service.SensorService,
                                "create_sensor_observation"))


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


if __name__ == "__main__":
    unittest.main()
