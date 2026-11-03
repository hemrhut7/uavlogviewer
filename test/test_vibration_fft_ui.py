"""
test_vibration_fft_ui.py — Integration tests for vibration and FFT operations in SidebarWidget and DataCalcDialog.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QPushButton
from uavlogviewer.models.chart_store import ChartStore, CalcBuilderState
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.gui.sidebar import SidebarWidget
from uavlogviewer.widgets.data_calc_dialog import DataCalcDialog
from uavlogviewer.widgets.fft_selection_dialog import FFTSelectionDialog

app = QApplication.instance() or QApplication([])


class TestVibrationFFTUI(unittest.TestCase):
    def setUp(self):
        self.chart_store = ChartStore()
        self.sidebar = SidebarWidget(self.chart_store)
        self.log = ParsedLog(filename="test_imu.bin", log_type="dataflash")

        # Create dummy IMU data at 100 Hz
        t = np.arange(0, 5.0, 0.01)  # 500 samples
        self.log.timestamps["IMU"] = t
        self.log.time_series["IMU.AccX"] = 1.0 * np.sin(2 * np.pi * 10 * t)
        self.log.time_series["IMU.AccY"] = 2.0 * np.sin(2 * np.pi * 20 * t)
        self.log.time_series["IMU.AccZ"] = 9.8 + 1.5 * np.sin(2 * np.pi * 30 * t)
        self.log.field_tree = {
            "IMU": ["AccX", "AccY", "AccZ"]
        }
        self.sidebar.populate_field_tree(self.log)

    def test_sidebar_inline_vibe(self):
        """Test inline calculation for 1D vibe in SidebarWidget."""
        chart_idx = 0
        self.sidebar.start_inline_builder(chart_idx)
        builder = self.chart_store.charts[chart_idx].pending_builder
        self.assertIsNotNone(builder)

        # Configure vibe operation on IMU.AccX
        builder.operator = "vibe"
        builder.operand_a = "IMU.AccX"
        self.sidebar.execute_inline_calc(chart_idx)

        # Result should be stored in time_series and added to chart
        res_name = "vibe(IMU.AccX)"
        self.assertIn(res_name, self.log.time_series)
        self.assertEqual(len(self.log.time_series[res_name]), 500)
        self.assertIn(res_name, [e.name for e in self.chart_store.charts[chart_idx].expressions])

    def test_sidebar_inline_vibe_mag(self):
        """Test inline calculation for 3D vibe_mag in SidebarWidget."""
        chart_idx = 0
        self.sidebar.start_inline_builder(chart_idx)
        builder = self.chart_store.charts[chart_idx].pending_builder
        self.assertIsNotNone(builder)

        # Configure vibe_mag with 3 axes
        builder.operator = "vibe_mag"
        builder.norm_operands = ["IMU.AccX", "IMU.AccY", "IMU.AccZ"]
        self.sidebar.execute_inline_calc(chart_idx)

        res_name = "vibe_mag(IMU.AccX, IMU.AccY, IMU.AccZ)"
        self.assertIn(res_name, self.log.time_series)
        self.assertEqual(len(self.log.time_series[res_name]), 500)
        self.assertIn(res_name, [e.name for e in self.chart_store.charts[chart_idx].expressions])

    def test_fft_action_is_available_on_scatter_not_calculate_data(self):
        """FFT is triggered from Scatter controls, not the math builder."""
        self.chart_store.add_xy_chart()

        fft_buttons = [
            button for button in self.sidebar.findChildren(QPushButton)
            if button.text() == "FFT"
        ]
        self.assertEqual(len(fft_buttons), 1)

        self.sidebar.start_inline_builder(0)
        combo_items = [
            combo.itemText(index)
            for combo in self.sidebar.findChildren(QComboBox)
            for index in range(combo.count())
        ]
        self.assertNotIn("fft", combo_items)

    def test_fft_selection_dialog_supports_multiple_checked_fields(self):
        dialog = FFTSelectionDialog(["IMU.AccX", "IMU.AccY", "IMU.AccZ"])
        dialog.set_field_checked("IMU.AccX", True)
        dialog.set_field_checked("IMU.AccY", True)

        self.assertEqual(
            dialog.selected_fields(),
            ["IMU.AccX", "IMU.AccY"]
        )

    def test_batch_fft_appends_pairs_without_overwriting_existing_scatter(self):
        chart_idx = self.chart_store.add_xy_chart("GPS.E", "GPS.N")
        existing_chart_count = len(self.chart_store.charts)

        self.sidebar.calculate_fft_for_fields(
            chart_idx, ["IMU.AccX", "IMU.AccY"]
        )

        chart = self.chart_store.charts[chart_idx]
        self.assertEqual(len(self.chart_store.charts), existing_chart_count)
        self.assertEqual(len(chart.pairs), 3)
        self.assertEqual((chart.pairs[0].x_field, chart.pairs[0].y_field), ("GPS.E", "GPS.N"))
        self.assertEqual(
            (chart.pairs[1].x_field, chart.pairs[1].y_field),
            ("FFT.freq_IMU_AccX", "FFT.mag_IMU_AccX")
        )
        self.assertEqual(
            (chart.pairs[2].x_field, chart.pairs[2].y_field),
            ("FFT.freq_IMU_AccY", "FFT.mag_IMU_AccY")
        )

    def test_batch_fft_fills_empty_pair_before_appending_more(self):
        chart_idx = self.chart_store.add_xy_chart()

        self.sidebar.calculate_fft_for_fields(
            chart_idx, ["IMU.AccX", "IMU.AccY"]
        )

        chart = self.chart_store.charts[chart_idx]
        self.assertEqual(len(chart.pairs), 2)
        self.assertEqual(
            (chart.pairs[0].x_field, chart.pairs[0].y_field),
            ("FFT.freq_IMU_AccX", "FFT.mag_IMU_AccX")
        )
        self.assertEqual(
            (chart.pairs[1].x_field, chart.pairs[1].y_field),
            ("FFT.freq_IMU_AccY", "FFT.mag_IMU_AccY")
        )

    def test_scatter_fft_button_runs_selected_batch(self):
        chart_idx = self.chart_store.add_xy_chart()
        fft_button = self.sidebar.findChild(
            QPushButton, f"fft_scatter_button_{chart_idx}"
        )

        with patch("uavlogviewer.gui.sidebar.FFTSelectionDialog") as dialog_type:
            dialog = dialog_type.return_value
            dialog.exec.return_value = QDialog.Accepted
            dialog.selected_fields.return_value = ["IMU.AccX", "IMU.AccY"]

            fft_button.click()

        chart = self.chart_store.charts[chart_idx]
        self.assertEqual(len(chart.pairs), 2)
        self.assertEqual(chart.pairs[0].x_field, "FFT.freq_IMU_AccX")
        self.assertEqual(chart.pairs[1].x_field, "FFT.freq_IMU_AccY")

    def test_data_calc_dialog_vibe_and_fft(self):
        """Test DataCalcDialog vibration and FFT calculation."""
        # 1. Test Single-axis vibration in dialog
        dialog = DataCalcDialog(self.log, target_chart_idx=0, chart_store=self.chart_store)
        dialog.radio_vibe.setChecked(True)
        dialog.combo_field_a.setCurrentText("IMU.AccZ")
        dialog.op_combo.setCurrentIndex(0)  # Single Axis
        dialog.perform_calculation()

        res_vibe = "vibe(IMU.AccZ)"
        self.assertIn(res_vibe, self.log.time_series)
        self.assertIn(res_vibe, [e.name for e in self.chart_store.charts[0].expressions])

        # 2. Test FFT in dialog
        dialog_fft = DataCalcDialog(self.log, target_chart_idx=0, chart_store=self.chart_store)
        dialog_fft.radio_fft.setChecked(True)
        dialog_fft.combo_field_a.setCurrentText("IMU.AccY")
        dialog_fft.perform_calculation()

        self.assertIn("FFT.freq_IMU_AccY", self.log.time_series)
        self.assertIn("FFT.mag_IMU_AccY", self.log.time_series)
