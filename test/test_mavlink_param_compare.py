import unittest
import os
import tempfile
from uavlogviewer.mavlink.param_comparator import (
    parse_param_file,
    is_protected_param,
    compare_parameters,
    ParamDiffItem,
    ParamStatus,
)


class TestParamComparator(unittest.TestCase):
    def test_parse_param_file_comma_and_space(self):
        content = """# MAVLink parameter file
ATC_RAT_PIT_P,0.185
ATC_RAT_RLL_P 0.220
# A comment line
SERIAL2_BAUD, 921.0
INVALID_LINE_NO_VAL
"""
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".param") as tf:
            tf.write(content)
            temp_path = tf.name

        try:
            params = parse_param_file(temp_path)
            self.assertIn("ATC_RAT_PIT_P", params)
            self.assertAlmostEqual(params["ATC_RAT_PIT_P"], 0.185)
            self.assertIn("ATC_RAT_RLL_P", params)
            self.assertAlmostEqual(params["ATC_RAT_RLL_P"], 0.220)
            self.assertIn("SERIAL2_BAUD", params)
            self.assertAlmostEqual(params["SERIAL2_BAUD"], 921.0)
            self.assertEqual(len(params), 3)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_is_protected_param(self):
        # Protected items
        is_prot, reason = is_protected_param("COMPASS_OFS_X")
        self.assertTrue(is_prot)
        self.assertIn("Calibration", reason)

        is_prot, reason = is_protected_param("INS_ACC_ID")
        self.assertTrue(is_prot)
        self.assertIn("Hardware ID", reason)

        is_prot, reason = is_protected_param("CAN_D1_DEVID")
        self.assertTrue(is_prot)
        self.assertIn("Hardware ID", reason)

        is_prot, reason = is_protected_param("BARO1_GND_PRESS")
        self.assertTrue(is_prot)

        # Non-protected items
        is_prot, reason = is_protected_param("ATC_RAT_PIT_P")
        self.assertFalse(is_prot)

        is_prot, reason = is_protected_param("Q_A_RAT_PIT_I")
        self.assertFalse(is_prot)

    def test_compare_parameters(self):
        fc_params = {
            "ATC_RAT_PIT_P": 0.150,
            "ATC_RAT_RLL_P": 0.185,
            "COMPASS_OFS_X": -142.5,
            "UNCHANGED_PARAM": 1.0,
        }
        target_params = {
            "ATC_RAT_PIT_P": 0.185,
            "ATC_RAT_RLL_P": 0.185,
            "COMPASS_OFS_X": -18.0,
            "UNCHANGED_PARAM": 1.00000001,  # Within tolerance
            "NEW_TARGET_PARAM": 42.0,       # Missing in FC
        }

        diffs = compare_parameters(fc_params, target_params, tol=1e-5)
        diff_dict = {item.name: item for item in diffs}

        # ATC_RAT_PIT_P modified
        p1 = diff_dict["ATC_RAT_PIT_P"]
        self.assertEqual(p1.status, ParamStatus.MODIFIED)
        self.assertTrue(p1.is_checked)
        self.assertFalse(p1.is_protected)
        self.assertAlmostEqual(p1.delta, 0.035)

        # ATC_RAT_RLL_P matches
        p2 = diff_dict["ATC_RAT_RLL_P"]
        self.assertEqual(p2.status, ParamStatus.MATCH)
        self.assertFalse(p2.is_checked)

        # COMPASS_OFS_X is protected calibration
        p3 = diff_dict["COMPASS_OFS_X"]
        self.assertEqual(p3.status, ParamStatus.PROTECTED)
        self.assertTrue(p3.is_protected)
        self.assertFalse(p3.is_checked)  # Must be unchecked by default for safe guard

        # UNCHANGED_PARAM within tol
        p4 = diff_dict["UNCHANGED_PARAM"]
        self.assertEqual(p4.status, ParamStatus.MATCH)

        # NEW_TARGET_PARAM missing in FC
        p5 = diff_dict["NEW_TARGET_PARAM"]
        self.assertEqual(p5.status, ParamStatus.MISSING_IN_FC)
        self.assertTrue(p5.is_checked)


if __name__ == "__main__":
    unittest.main()
