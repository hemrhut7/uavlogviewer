"""
test_plot_container_stats.py — Unit test verifying viewport stats table format in PlotContainer.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
import numpy as np
from PySide6.QtWidgets import QApplication, QHeaderView
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.gui.plot_container import PlotContainer

app = QApplication.instance() or QApplication([])

class TestPlotContainerStats(unittest.TestCase):
    def setUp(self):
        self.chart_store = ChartStore()
        self.log = ParsedLog(filename="test_flight.bin", log_type="dataflash")
        t_arr = np.linspace(0.0, 10.0, 100)
        self.log.timestamps["ATT"] = t_arr
        self.log.time_series["ATT.Roll"] = np.sin(t_arr)
        self.log.field_tree = {"ATT": ["Roll"]}

    def test_stats_table_chart_column_format(self):
        container = PlotContainer(self.chart_store)
        container.set_parsed_log(self.log)

        # Add expression to Chart #1 (index 0)
        self.chart_store.add_expression(0, "ATT.Roll")
        container.update_stats_for_range(0.0, 5.0)

        # Check that the stats table has 1 row and the first column is "#1", not "Chart #1"
        self.assertEqual(container.stats_table.rowCount(), 1)
        chart_item = container.stats_table.item(0, 0)
        self.assertIsNotNone(chart_item)
        self.assertEqual(chart_item.text(), "#1")

    def test_stats_table_column_resize_modes(self):
        container = PlotContainer(self.chart_store)
        header = container.stats_table.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(0), QHeaderView.ResizeToContents)
        self.assertEqual(header.sectionResizeMode(1), QHeaderView.Stretch)
        for col in range(2, 7):
            self.assertEqual(header.sectionResizeMode(col), QHeaderView.ResizeToContents)
