"""
test_csv_exporter_multi.py — Unit tests for CSV exporter with multiple logs.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
import numpy as np
import pandas as pd
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.models.log_session import LogSession
from uavlogviewer.tools.csv_exporter import export_plotted_data_to_dataframe

class TestCsvExporterMulti(unittest.TestCase):
    def setUp(self):
        self.store = ChartStore()

        self.log1 = ParsedLog(filename="flight1.bin", log_type="dataflash")
        t1 = np.array([100.0, 101.0, 102.0])
        self.log1.timestamps["ATT"] = t1
        self.log1.time_series["ATT.Roll"] = np.array([1.0, 2.0, 3.0])
        self.log1.field_tree = {"ATT": ["Roll"]}

        self.log2 = ParsedLog(filename="flight2.bin", log_type="dataflash")
        t2 = np.array([500.0, 501.0, 502.0])
        self.log2.timestamps["ATT"] = t2
        self.log2.time_series["ATT.Roll"] = np.array([10.0, 20.0, 30.0])
        self.log2.field_tree = {"ATT": ["Roll"]}

    def test_single_log_legacy_columns(self):
        self.store.add_expression(0, "ATT.Roll")
        df = export_plotted_data_to_dataframe(self.log1, self.store)
        self.assertIn("ATT.Roll", df.columns)
        self.assertNotIn("F1.ATT.Roll", df.columns)
        self.assertAlmostEqual(df["timestamp"].iloc[0], 100.0)

    def test_multi_log_prefixed_columns_and_zero_alignment(self):
        session = LogSession()
        l1 = session.add_log(self.log1, "/path/flight1.bin")
        l2 = session.add_log(self.log2, "/path/flight2.bin")

        self.store.add_expression(0, "ATT.Roll", log_id=l1.log_id)
        self.store.add_expression(0, "ATT.Roll", log_id=l2.log_id)

        df = export_plotted_data_to_dataframe(session, self.store)
        self.assertIn("timestamp", df.columns)
        self.assertIn("F1.ATT.Roll", df.columns)
        self.assertIn("F2.ATT.Roll", df.columns)
        # Shifted timestamps start at 0.0
        self.assertAlmostEqual(df["timestamp"].iloc[0], 0.0)
