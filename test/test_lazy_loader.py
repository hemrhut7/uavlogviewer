import unittest
import numpy as np
from uavlogviewer.parsers.base_parser import ParsedLog, LazyTimeSeriesDict, LazyTimestampsDict
from uavlogviewer.parsers.dataflash_parser import _clean_str

class TestLazyLoader(unittest.TestCase):
    def test_clean_str(self):
        self.assertEqual(_clean_str(b'ARMING_CHECK\x00\x00'), "ARMING_CHECK")
        self.assertEqual(_clean_str(b'Flight mode changed\x00'), "Flight mode changed")
        self.assertEqual(_clean_str("NORMAL_STR"), "NORMAL_STR")
        self.assertEqual(_clean_str("PADDED_STR\x00"), "PADDED_STR")

    def test_lazy_dicts_trigger(self):
        loaded = []

        def mock_loader(mtype):
            loaded.append(mtype)
            if mtype == "ATT":
                parsed.time_series["ATT.Roll"] = np.array([1.0, 2.0, 3.0])
                parsed.time_series["ATT.Pitch"] = np.array([0.1, 0.2, 0.3])
                parsed.timestamps["ATT"] = np.array([0.0, 0.1, 0.2])
            elif mtype == "IMU":
                parsed.time_series["IMU[0].AccX"] = np.array([0.0, 0.5])
                parsed.timestamps["IMU[0]"] = np.array([0.0, 0.05])

        parsed = ParsedLog(filename="test.bin", log_type="dataflash")
        parsed.field_tree = {
            "ATT": ["Roll", "Pitch"],
            "IMU[0]": ["AccX", "AccY"],
        }
        parsed.time_series = LazyTimeSeriesDict(parsed, loader=mock_loader)
        parsed.timestamps = LazyTimestampsDict(parsed, loader=mock_loader)

        # Invariant checks: ATT.Roll is in time_series, but raw message 'ATT' is NOT
        self.assertIn("ATT.Roll", parsed.time_series)
        self.assertNotIn("ATT", parsed.time_series)
        self.assertIn("ATT", parsed.timestamps)
        self.assertIn("IMU[0]", parsed.timestamps)
        self.assertEqual(len(loaded), 0)
        self.assertEqual(len(parsed.time_series), 4)

        # Access ATT.Roll
        roll = parsed.time_series["ATT.Roll"]
        self.assertEqual(len(roll), 3)
        self.assertEqual(loaded, ["ATT"])

        # Access ATT.Pitch - should NOT trigger loader again
        pitch = parsed.time_series["ATT.Pitch"]
        self.assertEqual(len(pitch), 3)
        self.assertEqual(loaded, ["ATT"])

        # Access bracketed instance field IMU[0].AccX
        accx = parsed.time_series["IMU[0].AccX"]
        self.assertEqual(len(accx), 2)
        self.assertEqual(loaded, ["ATT", "IMU"])

        # Access timestamps
        t = parsed.timestamps["ATT"]
        self.assertEqual(len(t), 3)

        # Accessing non-existent key raises KeyError
        with self.assertRaises(KeyError):
            _ = parsed.time_series["NON_EXISTENT.Field"]

    def test_estimated_rates_and_lookup(self):
        parsed = ParsedLog(filename="test.bin")
        parsed.estimated_rates = {
            "ATT": 25.0,
            "IMU[0]": 50.0,
        }
        self.assertEqual(parsed.get_data_rate("ATT"), 25.0)
        self.assertEqual(parsed.get_data_rate("IMU[0]"), 50.0)
        self.assertEqual(parsed.get_data_rate("ATT.Roll"), 25.0)
        self.assertEqual(parsed.get_data_rate("IMU[0].AccX"), 50.0)

if __name__ == "__main__":
    unittest.main()
