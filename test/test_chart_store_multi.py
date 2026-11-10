"""
test_chart_store_multi.py — Unit tests for ChartStore multi-file extensions.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from uavlogviewer.models.chart_store import ChartStore, ChartItem, XYScatterPair

class TestChartStoreMulti(unittest.TestCase):
    def setUp(self):
        self.store = ChartStore()

    def test_add_expression_with_log_id(self):
        # Adding same field name with different log_ids should both be added
        self.store.add_expression(0, "ATT.Roll", log_id=1)
        self.store.add_expression(0, "ATT.Roll", log_id=2)

        chart = self.store.charts[0]
        self.assertEqual(len(chart.expressions), 2)
        self.assertEqual(chart.expressions[0].name, "ATT.Roll")
        self.assertEqual(chart.expressions[0].log_id, 1)
        self.assertEqual(chart.expressions[1].name, "ATT.Roll")
        self.assertEqual(chart.expressions[1].log_id, 2)

        # Duplicate (same name AND same log_id) should be ignored
        self.store.add_expression(0, "ATT.Roll", log_id=1)
        self.assertEqual(len(chart.expressions), 2)

    def test_remove_expression_with_log_id(self):
        self.store.add_expression(0, "ATT.Roll", log_id=1)
        self.store.add_expression(0, "ATT.Roll", log_id=2)

        # Remove only log_id=1
        self.store.remove_expression(0, "ATT.Roll", log_id=1)
        chart = self.store.charts[0]
        self.assertEqual(len(chart.expressions), 1)
        self.assertEqual(chart.expressions[0].log_id, 2)

    def test_set_expression_axis_and_color_with_log_id(self):
        self.store.add_expression(0, "ATT.Roll", axis=0, log_id=1)
        self.store.add_expression(0, "ATT.Roll", axis=0, log_id=2)

        self.store.set_expression_axis(0, "ATT.Roll", axis=1, log_id=2)
        chart = self.store.charts[0]
        self.assertEqual(chart.expressions[0].axis, 0)
        self.assertEqual(chart.expressions[1].axis, 1)

        self.store.set_expression_color(0, "ATT.Roll", "#ff0000", log_id=2)
        self.assertEqual(chart.expressions[1].color, "#ff0000")

    def test_add_expression_for_logs(self):
        updated_calls = 0
        def on_update():
            nonlocal updated_calls
            updated_calls += 1
        self.store.updated.connect(on_update)

        self.store.add_expression_for_logs(0, "ATT.Pitch", [1, 2, 3])
        chart = self.store.charts[0]
        self.assertEqual(len(chart.expressions), 3)
        self.assertEqual(updated_calls, 1)  # Only one update signal emitted

    def test_duplicate_pair_for_logs(self):
        xy_idx = self.store.add_xy_chart("ATT.Roll", "ATT.Pitch")
        chart = self.store.charts[xy_idx]
        chart.pairs[0].log_id = 1

        self.store.duplicate_pair_for_logs(xy_idx, 0, [2, 3])
        self.assertEqual(len(chart.pairs), 3)
        self.assertEqual(chart.pairs[1].log_id, 2)
        self.assertEqual(chart.pairs[1].x_field, "ATT.Roll")
        self.assertEqual(chart.pairs[1].y_field, "ATT.Pitch")
        self.assertEqual(chart.pairs[2].log_id, 3)

    def test_remove_log(self):
        self.store.add_expression(0, "ATT.Roll", log_id=1)
        self.store.add_expression(0, "ATT.Pitch", log_id=2)
        xy_idx = self.store.add_xy_chart("ATT.Roll", "ATT.Pitch")
        self.store.charts[xy_idx].pairs[0].log_id = 1

        # Remove log 1
        self.store.remove_log(1)
        self.assertEqual(len(self.store.charts[0].expressions), 1)
        self.assertEqual(self.store.charts[0].expressions[0].log_id, 2)
        # In scatter, removing log 1 should reset or filter pair
        self.assertTrue(all(p.log_id != 1 for p in self.store.charts[xy_idx].pairs if p.x_field or p.y_field))
