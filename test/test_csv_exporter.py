"""
test_csv_exporter.py — Unit tests for exporting plotted messages and fields to CSV.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
import tempfile
import numpy as np
import pandas as pd
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.tools.csv_exporter import (
    get_plotted_messages_and_fields,
    get_all_fields_for_messages,
    export_plotted_data_to_dataframe,
    export_plotted_data_to_csv
)

class TestCsvExporter(unittest.TestCase):
    def setUp(self):
        self.chart_store = ChartStore()
        self.log = ParsedLog(filename="test_flight.bin", log_type="dataflash")

        # Message ATT: 50 Hz, 1 second (50 points)
        t_att = np.linspace(0.0, 1.0, 51)
        self.log.timestamps["ATT"] = t_att
        self.log.time_series["ATT.Roll"] = np.sin(t_att)
        self.log.time_series["ATT.Pitch"] = np.cos(t_att)
        self.log.time_series["ATT.Yaw"] = t_att * 10.0

        # Message GPS: 5 Hz, 1 second (6 points: 0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        t_gps = np.linspace(0.0, 1.0, 6)
        self.log.timestamps["GPS"] = t_gps
        self.log.time_series["GPS.Alt"] = 100.0 + t_gps * 5.0
        self.log.time_series["GPS.Spd"] = 15.0 + t_gps

        # Message CALC: custom expression
        self.log.timestamps["CALC"] = t_att
        self.log.time_series["CALC.diff"] = self.log.time_series["ATT.Roll"] - self.log.time_series["ATT.Pitch"]

        self.log.field_tree = {
            "ATT": ["Roll", "Pitch", "Yaw"],
            "GPS": ["Alt", "Spd"],
            "CALC": ["diff"]
        }

    def test_get_plotted_messages_and_fields_empty(self):
        msgs, fields = get_plotted_messages_and_fields(self.chart_store)
        self.assertEqual(msgs, [])
        self.assertEqual(fields, [])

    def test_get_plotted_messages_and_fields(self):
        self.chart_store.add_expression(0, "ATT.Roll")
        self.chart_store.add_expression(0, "GPS.Alt")
        msgs, fields = get_plotted_messages_and_fields(self.chart_store)
        self.assertIn("ATT", msgs)
        self.assertIn("GPS", msgs)
        self.assertIn("ATT.Roll", fields)
        self.assertIn("GPS.Alt", fields)

    def test_get_all_fields_for_messages(self):
        fields = get_all_fields_for_messages(self.log, ["ATT"])
        self.assertIn("ATT.Roll", fields)
        self.assertIn("ATT.Pitch", fields)
        self.assertIn("ATT.Yaw", fields)
        self.assertNotIn("GPS.Alt", fields)

    def test_export_single_message_plotted_fields(self):
        self.chart_store.add_expression(0, "ATT.Roll")
        self.chart_store.add_expression(0, "ATT.Pitch")

        df = export_plotted_data_to_dataframe(self.log, self.chart_store, scope="plotted_fields")
        self.assertIsNotNone(df)
        self.assertIn("timestamp", df.columns)
        self.assertIn("ATT.Roll", df.columns)
        self.assertIn("ATT.Pitch", df.columns)
        self.assertNotIn("ATT.Yaw", df.columns)
        self.assertEqual(len(df), 51)
        np.testing.assert_allclose(df["timestamp"].values, self.log.timestamps["ATT"])

    def test_export_multi_message_raw_union(self):
        # ATT (51 points) and GPS (6 points)
        self.chart_store.add_expression(0, "ATT.Roll")
        self.chart_store.add_expression(0, "GPS.Alt")

        df = export_plotted_data_to_dataframe(self.log, self.chart_store, scope="plotted_fields", fill_mode="none")
        self.assertIn("timestamp", df.columns)
        self.assertIn("ATT.Roll", df.columns)
        self.assertIn("GPS.Alt", df.columns)
        # All unique timestamps: 51 points (since GPS points 0, 0.2, 0.4, 0.6, 0.8, 1.0 are coincident with t_att)
        self.assertEqual(len(df), 51)
        # For non-GPS timestamps (e.g. idx 1 at 0.02), GPS.Alt should be NaN
        self.assertTrue(pd.isna(df.loc[1, "GPS.Alt"]))
        # At idx 0 (t=0.0) and idx 10 (t=0.2), GPS.Alt is not NaN
        self.assertFalse(pd.isna(df.loc[0, "GPS.Alt"]))
        self.assertAlmostEqual(df.loc[0, "GPS.Alt"], 100.0)

    def test_export_multi_message_forward_fill(self):
        self.chart_store.add_expression(0, "ATT.Roll")
        self.chart_store.add_expression(0, "GPS.Alt")

        df = export_plotted_data_to_dataframe(self.log, self.chart_store, scope="plotted_fields", fill_mode="ffill")
        self.assertIn("GPS.Alt", df.columns)
        # In forward-fill mode, idx 1 should have the same value as idx 0
        self.assertFalse(pd.isna(df.loc[1, "GPS.Alt"]))
        self.assertAlmostEqual(df.loc[1, "GPS.Alt"], 100.0)

    def test_export_full_messages_scope(self):
        # User plotted ATT.Roll; full_messages scope should export ATT.Roll, ATT.Pitch, ATT.Yaw
        self.chart_store.add_expression(0, "ATT.Roll")

        df = export_plotted_data_to_dataframe(self.log, self.chart_store, scope="full_messages")
        self.assertIn("timestamp", df.columns)
        self.assertIn("ATT.Roll", df.columns)
        self.assertIn("ATT.Pitch", df.columns)
        self.assertIn("ATT.Yaw", df.columns)
        self.assertNotIn("GPS.Alt", df.columns)

    def test_export_visible_time_range(self):
        self.chart_store.add_expression(0, "ATT.Roll")
        # Time range 0.2 to 0.6
        df = export_plotted_data_to_dataframe(
            self.log, self.chart_store, scope="plotted_fields", time_range=(0.2, 0.6)
        )
        self.assertTrue((df["timestamp"] >= 0.199).all())
        self.assertTrue((df["timestamp"] <= 0.601).all())
        self.assertTrue(len(df) > 0)
        self.assertTrue(len(df) < 51)

    def test_export_xy_scatter_pair(self):
        # Add XY scatter chart
        chart_idx = self.chart_store.add_xy_chart("ATT.Roll", "GPS.Alt")
        df = export_plotted_data_to_dataframe(self.log, self.chart_store, scope="plotted_fields")
        self.assertIn("ATT.Roll", df.columns)
        self.assertIn("GPS.Alt", df.columns)

    def test_export_to_csv_file(self):
        self.chart_store.add_expression(0, "ATT.Roll")
        self.chart_store.add_expression(0, "GPS.Alt")

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            num_rows = export_plotted_data_to_csv(self.log, self.chart_store, tmp_path)
            self.assertTrue(num_rows > 0)
            self.assertTrue(os.path.exists(tmp_path))
            
            # Read back and verify
            df_read = pd.read_csv(tmp_path)
            self.assertIn("timestamp", df_read.columns)
            self.assertIn("ATT.Roll", df_read.columns)
            self.assertIn("GPS.Alt", df_read.columns)
            self.assertEqual(len(df_read), num_rows)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_export_empty_chart_returns_empty_df(self):
        df = export_plotted_data_to_dataframe(self.log, self.chart_store)
        self.assertTrue(df.empty)

if __name__ == "__main__":
    unittest.main()
