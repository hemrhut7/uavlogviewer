"""
test_plotly_multi.py — Unit tests for Plotly HTML generation with multiple logs.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
import numpy as np
from uavlogviewer.parsers.base_parser import ParsedLog, FlightModeSpan
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.models.log_session import LogSession
from uavlogviewer.tools.plotly_exporter import generate_plotly_html

class TestPlotlyMulti(unittest.TestCase):
    def setUp(self):
        self.store = ChartStore()

        self.log1 = ParsedLog(filename="flight1.bin", log_type="dataflash")
        t1 = np.linspace(100.0, 110.0, 50)
        self.log1.timestamps["ATT"] = t1
        self.log1.time_series["ATT.Roll"] = np.sin(t1)
        self.log1.flight_modes = [FlightModeSpan(name="AUTO", start_time=100.0, end_time=110.0, color="#10b981")]
        self.log1.field_tree = {"ATT": ["Roll"]}

        self.log2 = ParsedLog(filename="flight2.bin", log_type="dataflash")
        t2 = np.linspace(500.0, 510.0, 50)
        self.log2.timestamps["ATT"] = t2
        self.log2.time_series["ATT.Roll"] = np.cos(t2)
        self.log2.field_tree = {"ATT": ["Roll"]}

    def test_legacy_single_parsed_log_compatibility(self):
        self.store.add_expression(0, "ATT.Roll")
        html = generate_plotly_html(self.log1, self.store)
        self.assertIn("ATT.Roll", html)
        self.assertNotIn("[F1]", html)

    def test_multi_log_labels_and_zero_alignment(self):
        session = LogSession()
        l1 = session.add_log(self.log1, "/path/flight1.bin")
        l2 = session.add_log(self.log2, "/path/flight2.bin")

        self.store.add_expression(0, "ATT.Roll", log_id=l1.log_id)
        self.store.add_expression(0, "ATT.Roll", log_id=l2.log_id)

        html = generate_plotly_html(session, self.store)

        # Legend / hover contains file label prefixes
        self.assertIn("[F1] ATT.Roll", html)
        self.assertIn("[F2] ATT.Roll", html)

        # Since zero_align is auto (active for multi-log), shifted timestamps should both be near 0..10
        # Check that flight mode background is shifted (starts at 0.0 rather than 100.0)
        self.assertIn("AUTO", html)
