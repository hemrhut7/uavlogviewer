"""
test_file_filter.py — Unit tests for file chooser dialog filter supporting .BIN and other uppercase extensions.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.gui.sidebar import SidebarWidget

app = QApplication.instance() or QApplication([])

class TestFileFilter(unittest.TestCase):
    def setUp(self):
        self.chart_store = ChartStore()
        self.sidebar = SidebarWidget(self.chart_store)

    @patch("uavlogviewer.gui.sidebar.QFileDialog.getOpenFileName")
    def test_choose_file_includes_bin_uppercase_filter(self, mock_get_open):
        mock_get_open.return_value = ("", "")
        self.sidebar.choose_file()

        mock_get_open.assert_called_once()
        args, kwargs = mock_get_open.call_args
        # args: (parent, caption, dir, filter)
        file_filter = args[3] if len(args) > 3 else kwargs.get("filter", "")

        # Verify that *.BIN is supported in the filter string
        self.assertIn("*.BIN", file_filter, "File filter should explicitly support uppercase *.BIN for Linux/case-sensitive systems")
        self.assertIn("*.bin", file_filter, "File filter should support lowercase *.bin")
