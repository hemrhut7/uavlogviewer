"""
test_log_summary.py — Unit tests for uavlogviewer.tools.log_summary module.
"""
import unittest
import numpy as np
from uavlogviewer.parsers.base_parser import ParsedLog, FlightModeSpan
from uavlogviewer.tools.log_summary import analyze_log_summary, FlightSpan


class TestLogSummary(unittest.TestCase):
    def test_empty_log(self):
        log = ParsedLog(filename="empty.tlog", log_type="tlog")
        summary = analyze_log_summary(log)
        self.assertEqual(summary.filename, "empty.tlog")
        self.assertFalse(summary.has_arming_data)
        self.assertFalse(summary.has_wind_data)
        self.assertEqual(summary.get_formatted_flight_time(), "N/A")
        self.assertIn("No wind data", summary.get_formatted_wind_speed())

    def test_single_arming_span_tlog(self):
        log = ParsedLog(filename="test.tlog", log_type="tlog")
        t_arr = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
        # 128 bit means armed (0x80)
        base_mode = np.array([0, 128, 128, 128, 0, 0])
        log.timestamps['HEARTBEAT[S1]'] = t_arr
        log.field_tree['HEARTBEAT[S1]'] = ['base_mode']
        log.time_series['HEARTBEAT[S1].base_mode'] = base_mode

        summary = analyze_log_summary(log)
        self.assertTrue(summary.has_arming_data)
        self.assertEqual(summary.flight_count, 1)
        self.assertIsNotNone(summary.longest_flight_span)
        self.assertAlmostEqual(summary.longest_flight_span.duration, 30.0)  # 50.0 - 20.0 = 30.0s
        self.assertIn("30s (30.0 s)", summary.get_formatted_flight_time())

    def test_multiple_arming_spans(self):
        log = ParsedLog(filename="multi_arm.bin", log_type="dataflash")
        t_arr = np.array([0, 10, 20, 30, 40, 50, 100, 200, 250, 300], dtype=float)
        # 0: disarmed, 1: armed
        armed_arr = np.array([0, 1, 1, 0, 0, 1, 1, 1, 0, 0])
        # Span 1: t=10 to 30 -> 20s
        # Span 2: t=50 to 250 -> 200s (longest)
        log.timestamps['STAT'] = t_arr
        log.field_tree['STAT'] = ['Armed']
        log.time_series['STAT.Armed'] = armed_arr

        summary = analyze_log_summary(log)
        self.assertTrue(summary.has_arming_data)
        self.assertEqual(summary.flight_count, 2)
        self.assertIsNotNone(summary.longest_flight_span)
        self.assertAlmostEqual(summary.longest_flight_span.duration, 200.0)
        self.assertIn("Longest of 2 flights", summary.get_formatted_flight_time())

    def test_wind_speed_calculation(self):
        log = ParsedLog(filename="wind.tlog", log_type="tlog")
        # Heartbeat arming span: 10 to 100
        t_hb = np.array([0.0, 10.0, 100.0, 110.0])
        base_mode = np.array([0, 128, 128, 0])
        log.timestamps['HEARTBEAT[S1]'] = t_hb
        log.field_tree['HEARTBEAT[S1]'] = ['base_mode']
        log.time_series['HEARTBEAT[S1].base_mode'] = base_mode

        # Wind data: t = [5, 20, 50, 80, 120]
        # Only [20, 50, 80] fall inside [10, 100]
        t_wind = np.array([5.0, 20.0, 50.0, 80.0, 120.0])
        w_spd = np.array([20.0, 2.0, 4.0, 6.0, 50.0])  # Flight values: 2, 4, 6
        log.timestamps['WIND[S1]'] = t_wind
        log.field_tree['WIND[S1]'] = ['speed']
        log.time_series['WIND[S1].speed'] = w_spd

        summary = analyze_log_summary(log)
        self.assertTrue(summary.has_wind_data)
        self.assertAlmostEqual(summary.avg_wind_speed_ms, 4.0)  # (2+4+6)/3 = 4.0
        self.assertAlmostEqual(summary.max_wind_speed_ms, 6.0)  # max(2,4,6) = 6.0
        self.assertIn("Avg: 4.0 m/s", summary.get_formatted_wind_speed())
        self.assertIn("Max: 6.0 m/s", summary.get_formatted_wind_speed())


if __name__ == '__main__':
    unittest.main()
