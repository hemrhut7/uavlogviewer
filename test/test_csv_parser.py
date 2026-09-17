"""
test_csv_parser.py — Unit tests for CsvParser supporting general and InertialLabs CSV logs.
"""
import os
import tempfile
import unittest
import numpy as np

from uavlogviewer.parsers.csv_parser import CsvParser


class TestCsvParser(unittest.TestCase):
    def setUp(self):
        self.parser = CsvParser()

    def test_parse_inertial_labs_imu_csv(self):
        content = (
            "# Start Time: 2026-09-17 14:36:51.977733\n"
            "wx,wy,wz,ax,ay,az,time\n"
            "11.09,-33.22,10.59,-1.66,1.28,11.00,572.000\n"
            "13.79,-29.49,10.49,-1.55,0.95,9.68,572.005\n"
            "16.80,-24.58,10.35,-1.40,0.34,7.95,572.010\n"
            "19.99,-19.35,10.55,-1.11,0.59,7.36,572.015\n"
            "# End Time: 2026-09-17 14:39:05.660193\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix="_InertialLabs IMU_test.csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            self.assertEqual(parsed.log_type, "csv")
            # Should identify IMU group
            self.assertIn("IMU", parsed.field_tree)
            fields = parsed.field_tree["IMU"]
            self.assertIn("wx", fields)
            self.assertIn("ax", fields)
            self.assertNotIn("time", fields)  # Time should be in timestamps, not data field

            # Check time series data
            self.assertIn("IMU.wx", parsed.time_series)
            np.testing.assert_allclose(parsed.time_series["IMU.wx"], [11.09, 13.79, 16.80, 19.99])
            np.testing.assert_allclose(parsed.time_series["IMU.az"], [11.00, 9.68, 7.95, 7.36])

            # Check timestamps
            self.assertIn("IMU", parsed.timestamps)
            np.testing.assert_allclose(parsed.timestamps["IMU"], [572.000, 572.005, 572.010, 572.015])

            # Check total log duration
            self.assertAlmostEqual(parsed.total_log_duration, 0.015, places=4)

            # Check rate estimation ~ 200 Hz
            rate = parsed.get_data_rate("IMU")
            self.assertAlmostEqual(rate, 200.0, places=1)

            # Check metadata preservation
            self.assertIn("Start_Time", parsed.params)
            self.assertEqual(parsed.params["Start_Time"], "2026-09-17 14:36:51.977733")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_parse_generic_csv_with_timestamp_column(self):
        content = (
            "Timestamp,Roll,Pitch,Yaw,Alt\n"
            "0.0,1.2,-0.5,120.4,10.0\n"
            "0.1,1.3,-0.4,120.5,10.2\n"
            "0.2,1.1,-0.6,120.3,10.5\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix="_attitude_log.csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            self.assertEqual(parsed.log_type, "csv")
            group = list(parsed.field_tree.keys())[0]
            self.assertIn("Roll", parsed.field_tree[group])
            self.assertIn("Alt", parsed.field_tree[group])
            self.assertNotIn("Timestamp", parsed.field_tree[group])

            np.testing.assert_allclose(parsed.timestamps[group], [0.0, 0.1, 0.2])
            np.testing.assert_allclose(parsed.time_series[f"{group}.Roll"], [1.2, 1.3, 1.1])
            self.assertAlmostEqual(parsed.total_log_duration, 0.2, places=4)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_parse_csv_without_time_column(self):
        content = (
            "var_a,var_b\n"
            "10.0,20.0\n"
            "11.0,21.0\n"
            "12.0,22.0\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            group = list(parsed.field_tree.keys())[0]
            self.assertEqual(len(parsed.timestamps[group]), 3)
            self.assertIn(f"{group}.var_a", parsed.time_series)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_parse_csv_with_dotted_columns(self):
        content = (
            "time,IMU.ax,IMU.ay,GPS.lat,GPS.lon\n"
            "0.0,1.0,2.0,25.0,121.0\n"
            "0.5,1.1,2.1,25.0001,121.0001\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            self.assertIn("IMU", parsed.field_tree)
            self.assertIn("GPS", parsed.field_tree)
            self.assertIn("ax", parsed.field_tree["IMU"])
            self.assertIn("lat", parsed.field_tree["GPS"])
            self.assertIn("IMU.ax", parsed.time_series)
            self.assertIn("GPS.lat", parsed.time_series)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_parse_param_csv(self):
        content = (
            "Parameter,Value\n"
            "COM1_bps,10.0\n"
            "Data_rate,200.0\n"
            "AutoStart,149.0\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix="_params.csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            self.assertEqual(parsed.log_type, "csv_param")
            self.assertIn("COM1_bps", parsed.params)
            self.assertEqual(parsed.params["COM1_bps"], 10.0)
            self.assertEqual(parsed.params["Data_rate"], 200.0)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_parse_semicolon_and_tab_delimiters(self):
        content = (
            "time;ax;ay;az\n"
            "0.0;1.0;2.0;3.0\n"
            "0.1;1.1;2.1;3.1\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            group = list(parsed.field_tree.keys())[0]
            self.assertIn(f"{group}.ax", parsed.time_series)
            np.testing.assert_allclose(parsed.timestamps[group], [0.0, 0.1])
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_parse_millisecond_timestamps(self):
        content = (
            "time(millisecond),gyro_x,gyro_y\n"
            "100000.0,0.1,0.2\n"
            "100050.0,0.2,0.3\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            group = list(parsed.field_tree.keys())[0]
            # 100000 ms -> 100.0 s, 100050 ms -> 100.05 s
            np.testing.assert_allclose(parsed.timestamps[group], [100.0, 100.05])
            self.assertAlmostEqual(parsed.total_log_duration, 0.05)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_ardupilot_timeus_scaling(self):
        content = (
            "TimeUS,Roll,Pitch\n"
            "200000000,1.0,2.0\n"
            "200020000,1.1,2.1\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            group = list(parsed.field_tree.keys())[0]
            # 200000000 us -> 200.0 s, 200020000 us -> 200.02 s
            np.testing.assert_allclose(parsed.timestamps[group], [200.0, 200.02])
            self.assertAlmostEqual(parsed.total_log_duration, 0.02)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_short_millisecond_scaling(self):
        content = (
            "time_ms,val\n"
            "1000,10\n"
            "1050,20\n"
            "1100,30\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            group = list(parsed.field_tree.keys())[0]
            # 1000 ms -> 1.0 s, 1100 ms -> 1.1 s
            np.testing.assert_allclose(parsed.timestamps[group], [1.0, 1.05, 1.1])
            self.assertAlmostEqual(parsed.total_log_duration, 0.1)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_double_slash_comments(self):
        content = (
            "// Sensor Configuration: 100Hz\n"
            "// Calibration Date: 2026-09-17\n"
            "time,ax,ay\n"
            "0.0,0.1,0.2\n"
            "0.01,0.15,0.25\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            group = list(parsed.field_tree.keys())[0]
            self.assertIn(f"{group}.ax", parsed.time_series)
            self.assertIn("Sensor_Configuration", parsed.params)
            np.testing.assert_allclose(parsed.timestamps[group], [0.0, 0.01])
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_datetime_first_row_invalid(self):
        content = (
            "timestamp,val\n"
            ",1.0\n"
            "2026-09-17 14:00:00.000,2.0\n"
            "2026-09-17 14:00:01.000,3.0\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            group = list(parsed.field_tree.keys())[0]
            t_arr = parsed.timestamps[group]
            # Should not be all NaNs or fail completely
            self.assertEqual(len(t_arr), 3)
            self.assertFalse(np.isnan(t_arr[1]))
            self.assertFalse(np.isnan(t_arr[2]))
            self.assertAlmostEqual(t_arr[2] - t_arr[1], 1.0)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_dotted_time_column(self):
        content = (
            "IMU.time,IMU.ax,IMU.ay\n"
            "0.0,1.0,2.0\n"
            "0.1,1.1,2.1\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            parsed = self.parser.parse(tmp_path)
            self.assertIn("IMU", parsed.field_tree)
            self.assertNotIn("time", parsed.field_tree["IMU"])
            self.assertIn("ax", parsed.field_tree["IMU"])
            np.testing.assert_allclose(parsed.timestamps["IMU"], [0.0, 0.1])
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_real_inertial_labs_imu_file_if_present(self):
        target = os.environ.get("INERTIAL_LABS_TEST_CSV")
        if not target or not os.path.exists(target):
            data_dir = "/home/hank/文件/Python/INS_Reader/data"
            if os.path.isdir(data_dir):
                import glob
                matches = glob.glob(os.path.join(data_dir, "InertialLabs IMU_*.csv"))
                if matches:
                    target = matches[0]

        if not target or not os.path.exists(target):
            self.skipTest("InertialLabs test CSV not configured or found")

        parsed = self.parser.parse(target)
        self.assertEqual(parsed.log_type, "csv")
        self.assertIn("IMU", parsed.field_tree)
        self.assertEqual(sorted(parsed.field_tree["IMU"]), ["ax", "ay", "az", "wx", "wy", "wz"])
        self.assertGreater(parsed.total_log_duration, 0.0)
        self.assertAlmostEqual(parsed.get_data_rate("IMU"), 2000.0, delta=10.0)
        self.assertIn("IMU.wx", parsed.time_series)
        self.assertGreater(len(parsed.time_series["IMU.wx"]), 1000)


if __name__ == "__main__":
    unittest.main()
