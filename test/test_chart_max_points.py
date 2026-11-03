"""
test_chart_max_points.py — Unit tests for chart max_points setting and time series downsampling behavior.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
import numpy as np
from uavlogviewer.models.chart_store import ChartStore, ChartPanel
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.tools.plotly_exporter import generate_plotly_html

class TestChartMaxPoints(unittest.TestCase):
    def setUp(self):
        self.chart_store = ChartStore()
        self.log = ParsedLog(filename="test_pts.bin", log_type="dataflash")
        
        # Create 20,000 data points
        t = np.linspace(0, 100, 20000)
        val = np.sin(t)
        self.log.timestamps["ATT"] = t
        self.log.time_series["ATT.Roll"] = val
        self.log.field_tree = {"ATT": ["Roll"]}

    def test_default_timeseries_max_points(self):
        panel = ChartPanel("Chart 1", chart_type="timeseries")
        self.assertEqual(panel.max_points, 10000)

    def test_default_scatter_max_points(self):
        panel = ChartPanel("Scatter 1", chart_type="scatter")
        self.assertEqual(panel.max_points, 5000)

    def test_set_chart_max_points(self):
        self.chart_store.set_chart_max_points(0, 0)
        self.assertEqual(self.chart_store.charts[0].max_points, 0)

        self.chart_store.set_chart_max_points(0, 50000)
        self.assertEqual(self.chart_store.charts[0].max_points, 50000)

    def test_unlimited_points_generation(self):
        # Set chart 0 to unlimited points (max_points = 0)
        self.chart_store.set_chart_max_points(0, 0)
        self.chart_store.add_expression(0, "ATT.Roll")
        
        html = generate_plotly_html(self.log, self.chart_store)
        self.assertIn("ATT.Roll", html)
        self.assertTrue(len(html) > 0)
        # When unlimited points or large dataset, hovermode should be disabled (false) to prevent event queue starvation
        self.assertIn('"hovermode":false', html.replace(' ', ''))
        # Verify debounce timer is present in JS
        self.assertIn("relayoutTimer", html)
        self.assertIn("setTimeout", html)

    def test_scatter_visible_range_filtering(self):
        # Create XY Scatter chart
        cs = ChartStore()
        cs.add_xy_chart("ATT.Pitch", "ATT.Roll")
        self.log.time_series["ATT.Pitch"] = np.cos(self.log.timestamps["ATT"])
        self.log.field_tree["ATT"].append("Pitch")

        # Full range
        html_full = generate_plotly_html(self.log, cs, visible_range=None)
        self.assertIn("XY Scatter", html_full)

        # Filtered range: 10s ~ 20s
        html_filtered = generate_plotly_html(self.log, cs, visible_range=(10.0, 20.0))
        self.assertIn("XY Scatter", html_filtered)
        # Verify range is preserved on timeline
        self.assertIn('"range":[10.0,20.0]', html_filtered.replace(' ', ''))

    def test_set_xy_pair_color(self):
        chart_idx = self.chart_store.add_xy_chart("ATT.Roll", "ATT.Roll")

        self.chart_store.set_xy_pair_color(chart_idx, 0, "#123456")

        self.assertEqual(self.chart_store.charts[chart_idx].pairs[0].color, "#123456")
        html = generate_plotly_html(self.log, self.chart_store)
        self.assertIn("#123456", html)

if __name__ == "__main__":
    unittest.main()
