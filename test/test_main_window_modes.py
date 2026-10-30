import os
import unittest
from unittest.mock import patch, MagicMock

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from uavlogviewer.gui.main_window import MainWindow


class TestMainWindowModeSwitching(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_mode_switcher_initial_state(self):
        self.assertEqual(self.window.main_stack.currentIndex(), 0)
        self.assertIn("Offline", self.window.lbl_active_mode_desc.text())

    def test_switch_to_live_mode(self):
        self.window.switch_mode(1)
        self.assertEqual(self.window.main_stack.currentIndex(), 1)
        self.assertIn("Live", self.window.lbl_active_mode_desc.text())

    def test_sidebar_switch_to_live_signal(self):
        self.window.switch_mode(0)
        self.window.sidebar.switch_to_live_requested.emit()
        self.assertEqual(self.window.main_stack.currentIndex(), 1)

    def test_live_widget_open_log_requested_switches_to_offline(self):
        self.window.switch_mode(1)
        with patch.object(self.window, "load_log_file") as mock_load:
            self.window.mavlink_live_widget.open_log_requested.emit("/fake/path/test.bin")
            self.assertEqual(self.window.main_stack.currentIndex(), 0)
            mock_load.assert_called_once_with("/fake/path/test.bin")


if __name__ == "__main__":
    unittest.main()
