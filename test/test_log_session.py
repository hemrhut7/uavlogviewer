"""
test_log_session.py — Unit tests for LogSession and LoadedLog models.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
import numpy as np
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.log_session import LogSession, LoadedLog, MAX_LOGS

class TestLogSession(unittest.TestCase):
    def setUp(self):
        self.session = LogSession()

    def _make_dummy_log(self, name: str, start_time: float = 100.0) -> ParsedLog:
        log = ParsedLog(filename=name, log_type="dataflash")
        t = np.linspace(start_time, start_time + 10.0, 50)
        log.timestamps["ATT"] = t
        log.time_series["ATT.Roll"] = np.sin(t)
        log.field_tree = {"ATT": ["Roll"]}
        return log

    def test_add_log_basic(self):
        log1 = self._make_dummy_log("flight1.bin", 150.0)
        loaded1 = self.session.add_log(log1, "/path/flight1.bin")
        self.assertIsNotNone(loaded1)
        self.assertEqual(loaded1.label, "F1")
        self.assertEqual(loaded1.t_first, 150.0)
        self.assertEqual(len(self.session.logs), 1)
        self.assertFalse(self.session.is_multi)
        self.assertEqual(self.session.active_log_id, loaded1.log_id)
        self.assertEqual(self.session.active_log, loaded1)

    def test_add_log_multi_and_labels(self):
        log1 = self._make_dummy_log("flight1.bin", 100.0)
        log2 = self._make_dummy_log("flight2.bin", 200.0)
        l1 = self.session.add_log(log1, "/path/flight1.bin")
        l2 = self.session.add_log(log2, "/path/flight2.bin")

        self.assertEqual(len(self.session.logs), 2)
        self.assertTrue(self.session.is_multi)
        self.assertEqual(l1.label, "F1")
        self.assertEqual(l2.label, "F2")

    def test_max_logs_limit(self):
        for i in range(MAX_LOGS):
            res = self.session.add_log(self._make_dummy_log(f"f{i}.bin"), f"/path/f{i}.bin")
            self.assertIsNotNone(res)
        self.assertEqual(len(self.session.logs), MAX_LOGS)

        # 9th log should be rejected
        res_9 = self.session.add_log(self._make_dummy_log("f9.bin"), "/path/f9.bin")
        self.assertIsNone(res_9)
        self.assertEqual(len(self.session.logs), MAX_LOGS)

    def test_duplicate_filepath(self):
        log1 = self._make_dummy_log("flight1.bin")
        self.session.add_log(log1, "/path/flight1.bin")
        res_dup = self.session.add_log(log1, "/path/flight1.bin")
        self.assertIsNone(res_dup)
        self.assertEqual(len(self.session.logs), 1)

    def test_remove_log_and_label_reuse(self):
        l1 = self.session.add_log(self._make_dummy_log("f1.bin"), "/path/f1.bin")
        l2 = self.session.add_log(self._make_dummy_log("f2.bin"), "/path/f2.bin")
        l3 = self.session.add_log(self._make_dummy_log("f3.bin"), "/path/f3.bin")

        # Active is initially l1
        self.assertEqual(self.session.active_log_id, l1.log_id)

        # Remove l1: active switches to l2
        self.session.remove_log(l1.log_id)
        self.assertEqual(len(self.session.logs), 2)
        self.assertEqual(self.session.active_log_id, l2.log_id)

        # Add new log: should reuse F1 label
        l4 = self.session.add_log(self._make_dummy_log("f4.bin"), "/path/f4.bin")
        self.assertEqual(l4.label, "F1")

    def test_zero_align_mode_and_time_shift(self):
        l1 = self.session.add_log(self._make_dummy_log("f1.bin", 100.0), "/path/f1.bin")
        l2 = self.session.add_log(self._make_dummy_log("f2.bin", 500.0), "/path/f2.bin")

        # By default auto: multi-log -> zero_align_enabled is True
        self.assertTrue(self.session.zero_align_enabled)
        self.assertAlmostEqual(self.session.time_shift(l1.log_id), -100.0)
        self.assertAlmostEqual(self.session.time_shift(l2.log_id), -500.0)

        # Add user offset
        l2.user_offset = 5.0
        self.assertAlmostEqual(self.session.time_shift(l2.log_id), -495.0)

        # Force off
        self.session.zero_align_mode = "off"
        self.assertFalse(self.session.zero_align_enabled)
        self.assertAlmostEqual(self.session.time_shift(l1.log_id), 0.0)
        self.assertAlmostEqual(self.session.time_shift(l2.log_id), 5.0)

        # Force on with single log
        self.session.remove_log(l2.log_id)
        self.assertFalse(self.session.is_multi)
        self.session.zero_align_mode = "auto"
        self.assertFalse(self.session.zero_align_enabled)
        self.session.zero_align_mode = "on"
        self.assertTrue(self.session.zero_align_enabled)
        self.assertAlmostEqual(self.session.time_shift(l1.log_id), -100.0)

    def test_display_name(self):
        l1 = self.session.add_log(self._make_dummy_log("f1.bin"), "/path/f1.bin")
        # Single log: no prefix
        self.assertEqual(self.session.display_name("ATT.Roll", l1.log_id), "ATT.Roll")

        l2 = self.session.add_log(self._make_dummy_log("f2.bin"), "/path/f2.bin")
        # Multi log: prefixes
        self.assertEqual(self.session.display_name("ATT.Roll", l1.log_id), "[F1] ATT.Roll")
        self.assertEqual(self.session.display_name("ATT.Roll", l2.log_id), "[F2] ATT.Roll")

    def test_flight_mode_source(self):
        l1 = self.session.add_log(self._make_dummy_log("f1.bin"), "/path/f1.bin")
        l2 = self.session.add_log(self._make_dummy_log("f2.bin"), "/path/f2.bin")

        self.assertEqual(self.session.flight_mode_source, "active")
        self.assertEqual(self.session.flight_mode_log(), l1)

        self.session.flight_mode_source = str(l2.log_id)
        self.assertEqual(self.session.flight_mode_log(), l2)

        self.session.flight_mode_source = "none"
        self.assertIsNone(self.session.flight_mode_log())

    def test_from_parsed_log(self):
        log = self._make_dummy_log("single.bin", 50.0)
        session = LogSession.from_parsed_log(log)
        self.assertEqual(len(session.logs), 1)
        self.assertEqual(session.logs[0].parsed, log)
        self.assertEqual(session.logs[0].label, "F1")
        self.assertEqual(session.logs[0].t_first, 50.0)
