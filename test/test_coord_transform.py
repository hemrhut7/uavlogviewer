"""
test_coord_transform.py — Unit tests for ENU coordinate transformation engine.
"""
import unittest
import numpy as np
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.tools.coord_transform import (
    earth_radii,
    llh2enu,
    convert_llh_series_to_enu,
    detect_llh_messages
)

class TestCoordTransform(unittest.TestCase):
    def test_earth_radii(self):
        # At equator (lat = 0)
        rm, rn = earth_radii(0.0)
        self.assertAlmostEqual(rn, 6378137.0, places=1)
        self.assertLess(rm, rn)  # Meridian radius < prime vertical radius at equator

    def test_llh2enu_origin(self):
        # Test origin point returns [0, 0, 0]
        pos0 = np.radians([23.973875, 120.982025, 100.0])
        enu = llh2enu(pos0, pos0)
        np.testing.assert_allclose(enu, [0.0, 0.0, 0.0], atol=1e-6)

    def test_llh2enu_delta(self):
        # Test small shift north & east
        lat0_deg, lon0_deg, alt0 = 24.0, 121.0, 50.0
        ref_pos = np.array([np.radians(lat0_deg), np.radians(lon0_deg), alt0])

        # 0.001 deg north shift ~ 111 meters north
        dlat_deg = 0.001
        target_pos = np.array([np.radians(lat0_deg + dlat_deg), np.radians(lon0_deg), alt0 + 5.0])
        enu = llh2enu(target_pos, ref_pos)

        self.assertAlmostEqual(enu[0], 0.0, delta=0.1)  # East ~ 0
        self.assertGreater(enu[1], 100.0)              # North ~ 111m
        self.assertLess(enu[1], 120.0)
        self.assertAlmostEqual(enu[2], 5.0, places=4)   # Up = 5m

    def test_convert_llh_series(self):
        lats = np.array([23.973875, 23.973975, 23.974075])
        lons = np.array([120.982025, 120.982125, 120.982225])
        alts = np.array([100.0, 102.5, 105.0])

        e, n, u, origin = convert_llh_series_to_enu(lats, lons, alts)

        self.assertEqual(len(e), 3)
        self.assertEqual(len(n), 3)
        self.assertEqual(len(u), 3)
        # First point should be origin (0, 0, 0)
        self.assertAlmostEqual(e[0], 0.0)
        self.assertAlmostEqual(n[0], 0.0)
        self.assertAlmostEqual(u[0], 0.0)
        self.assertAlmostEqual(origin[0], 23.973875)
        self.assertAlmostEqual(origin[1], 120.982025)
        self.assertAlmostEqual(origin[2], 100.0)

    def test_convert_scaled_1e7(self):
        # Test DataFlash 1e7 scaled lat/lon integers
        lats = np.array([239738750, 239739750])
        lons = np.array([1209820250, 1209821250])
        alts = np.array([50.0, 52.0])

        e, n, u, origin = convert_llh_series_to_enu(lats, lons, alts)
        self.assertAlmostEqual(origin[0], 23.973875)
        self.assertAlmostEqual(origin[1], 120.982025)
        self.assertAlmostEqual(e[0], 0.0)

    def test_detect_llh_messages(self):
        parsed = ParsedLog()
        parsed.field_tree = {
            "GPS": ["Status", "Lat", "Lng", "Alt", "Spd"],
            "POS": ["Lat", "Lng", "Alt", "RelHomeAlt"],
            "ATT": ["Roll", "Pitch", "Yaw"]
        }
        parsed.time_series = {
            "GPS.Lat": np.array([24.0, 24.01]),
            "GPS.Lng": np.array([121.0, 121.01]),
            "GPS.Alt": np.array([10.0, 12.0]),
            "POS.Lat": np.array([24.0, 24.01]),
            "POS.Lng": np.array([121.0, 121.01]),
            "POS.Alt": np.array([10.0, 12.0]),
            "ATT.Roll": np.array([0.0, 0.1]),
        }

        candidates = detect_llh_messages(parsed)
        self.assertEqual(len(candidates), 2)
        msg_types = [c['msg_type'] for c in candidates]
        self.assertIn("GPS", msg_types)
        self.assertIn("POS", msg_types)

    def test_coord_transform_dialog_calculation(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication, QMessageBox
        from uavlogviewer.models.chart_store import ChartStore
        from uavlogviewer.widgets.coord_transform_dialog import CoordTransformDialog

        app = QApplication.instance() or QApplication([])

        parsed = ParsedLog()
        parsed.field_tree = {
            "GPS": ["Lat", "Lng", "Alt"]
        }
        parsed.time_series = {
            "GPS.Lat": np.array([24.0, 24.001, 24.002]),
            "GPS.Lng": np.array([121.0, 121.001, 121.002]),
            "GPS.Alt": np.array([50.0, 52.0, 55.0])
        }
        parsed.timestamps = {
            "GPS": np.array([0.0, 0.1, 0.2])
        }

        chart_store = ChartStore()
        chart_idx = chart_store.add_xy_chart()

        dialog = CoordTransformDialog(parsed, chart_store, target_chart_idx=chart_idx)
        self.assertEqual(dialog.msg_list.count(), 1)

        with patch.object(QMessageBox, 'information', return_value=QMessageBox.Ok):
            dialog.calculate_enu()

        self.assertIn("CALC.GPS_E", parsed.time_series)
        self.assertIn("CALC.GPS_N", parsed.time_series)
        self.assertIn("CALC.GPS_U", parsed.time_series)
        self.assertIn("CALC", parsed.field_tree)
        self.assertIn("GPS_E", parsed.field_tree["CALC"])

        # Check chart pairs updated
        chart = chart_store.charts[chart_idx]
        self.assertEqual(chart.x_field, "CALC.GPS_E")
        self.assertEqual(chart.y_field, "CALC.GPS_N")

    def test_convert_llh_series_with_zero_unfixed_points(self):
        # Initial 2 points at (0,0) before satellite lock, then valid flight
        lats = np.array([0.0, 0.0, 24.0, 24.001])
        lons = np.array([0.0, 0.0, 121.0, 121.001])
        alts = np.array([0.0, 0.0, 50.0, 52.0])

        e, n, u, origin = convert_llh_series_to_enu(lats, lons, alts)

        # Origin should be index 2 (24.0, 121.0, 50.0), NOT (0,0,0)
        self.assertAlmostEqual(origin[0], 24.0)
        self.assertAlmostEqual(origin[1], 121.0)
        self.assertAlmostEqual(origin[2], 50.0)

        # Index 0 and 1 should be NaN
        self.assertTrue(np.isnan(e[0]))
        self.assertTrue(np.isnan(n[0]))
        self.assertTrue(np.isnan(e[1]))

        # Index 2 should be (0, 0, 0)
        self.assertAlmostEqual(e[2], 0.0)
        self.assertAlmostEqual(n[2], 0.0)
        self.assertAlmostEqual(u[2], 0.0)

    def test_get_series_data_and_timestamps(self):
        from uavlogviewer.tools.plotly_exporter import get_series_data_and_timestamps

        parsed = ParsedLog()
        parsed.time_series["CALC.GPS_E"] = np.array([1.0, 2.0, 3.0])
        parsed.timestamps["CALC.GPS_E"] = np.array([10.0, 11.0, 12.0])

        # Test lookup with prefix
        t, y = get_series_data_and_timestamps(parsed, "CALC.GPS_E")
        self.assertEqual(len(y), 3)
        self.assertEqual(y[0], 1.0)

        # Test lookup without CALC. prefix
        t2, y2 = get_series_data_and_timestamps(parsed, "GPS_E")
        self.assertEqual(len(y2), 3)
        self.assertEqual(y2[0], 1.0)

if __name__ == "__main__":
    unittest.main()
