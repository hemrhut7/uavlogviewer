"""
test_export_csv_dialog.py — Unit tests for ExportCsvDialog.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
import tempfile
import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.widgets.export_csv_dialog import ExportCsvDialog

app = QApplication.instance() or QApplication([])

class TestExportCsvDialog(unittest.TestCase):
    def setUp(self):
        self.chart_store = ChartStore()
        self.log = ParsedLog(filename="test_flight.bin", log_type="dataflash")

        t_att = np.linspace(0.0, 1.0, 20)
        self.log.timestamps["ATT"] = t_att
        self.log.time_series["ATT.Roll"] = np.sin(t_att)
        self.log.time_series["ATT.Pitch"] = np.cos(t_att)
        self.log.field_tree = {"ATT": ["Roll", "Pitch"]}

    def test_dialog_with_no_plotted_fields(self):
        dialog = ExportCsvDialog(self.log, self.chart_store)
        self.assertFalse(dialog.btn_export.isEnabled())
        self.assertIn("沒有繪製任何欄位", dialog.lbl_status.text())

    def test_dialog_with_plotted_fields(self):
        self.chart_store.add_expression(0, "ATT.Roll")
        dialog = ExportCsvDialog(self.log, self.chart_store, visible_range=(0.2, 0.8))
        self.assertTrue(dialog.btn_export.isEnabled())
        self.assertIn("ATT", dialog.lbl_status.text())

        # Test export execution to temp file
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            success = dialog.execute_export(tmp_path)
            self.assertTrue(success)
            self.assertTrue(os.path.exists(tmp_path))
            df = pd.read_csv(tmp_path)
            self.assertIn("timestamp", df.columns)
            self.assertIn("ATT.Roll", df.columns)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_main_window_integration(self):
        from uavlogviewer.gui.main_window import MainWindow
        win = MainWindow()
        win.parsed_log = self.log
        win.chart_store = self.chart_store
        self.chart_store.add_expression(0, "ATT.Roll")

        # Test on_csv_exported slot
        win.on_csv_exported("/tmp/test_out.csv", 42)
        self.assertIn("test_out.csv", win.status_bar.currentMessage())
        self.assertIn("42 列", win.status_bar.currentMessage())

if __name__ == "__main__":
    unittest.main()
