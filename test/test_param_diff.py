"""
test_param_diff.py — Unit tests for parameter difference analysis.
"""
import unittest
from uavlogviewer.tools.param_diff import compute_param_diff

class TestParamDiff(unittest.TestCase):
    def test_compute_param_diff_all_and_filtered(self):
        p1 = {"ARMING_CHECK": 1, "BATT_CAPACITY": 5000, "ATC_RAT_RLL_P": 0.135}
        p2 = {"ARMING_CHECK": 1, "BATT_CAPACITY": 5200, "ATC_RAT_RLL_P": 0.1350001, "NEW_PARAM": 42}
        params_by_label = {"F1": p1, "F2": p2}

        # only_diff=True with tol=1e-5:
        # ARMING_CHECK is identical -> omitted
        # ATC_RAT_RLL_P diff is 1e-7 < tol -> omitted
        # BATT_CAPACITY differs (5000 vs 5200) -> kept
        # NEW_PARAM is missing in F1 -> kept
        diff = compute_param_diff(params_by_label, only_diff=True, tol=1e-5)
        diff_names = [row[0] for row in diff]
        self.assertIn("BATT_CAPACITY", diff_names)
        self.assertIn("NEW_PARAM", diff_names)
        self.assertNotIn("ARMING_CHECK", diff_names)
        self.assertNotIn("ATC_RAT_RLL_P", diff_names)

        # only_diff=False: all 4 params included
        all_params = compute_param_diff(params_by_label, only_diff=False)
        self.assertEqual(len(all_params), 4)

    def test_compute_param_diff_string_values(self):
        p1 = {"SYS_NAME": "Alpha", "MODE": "AUTO"}
        p2 = {"SYS_NAME": "Beta", "MODE": "AUTO"}
        diff = compute_param_diff({"F1": p1, "F2": p2}, only_diff=True)
        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0][0], "SYS_NAME")
        self.assertEqual(diff[0][1], ["Alpha", "Beta"])
