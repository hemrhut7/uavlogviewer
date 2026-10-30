import os
import unittest
from unittest.mock import patch, MagicMock

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from uavlogviewer.widgets.mavlink_live_widget import MavlinkLiveWidget


class TestMavlinkLiveWidget(unittest.TestCase):
    def setUp(self):
        self.widget = MavlinkLiveWidget()

    def test_widget_tabs_exist_and_no_motor_test(self):
        # Tabs should be: Params & Compare, Commands, Joystick, Onboard Logs
        tab_names = [self.widget.left_tabs.tabText(i) for i in range(self.widget.left_tabs.count())]
        self.assertTrue(any("Params" in name for name in tab_names))
        self.assertTrue(any("Commands" in name for name in tab_names))
        self.assertTrue(any("Joystick" in name for name in tab_names))
        self.assertTrue(any("Logs" in name for name in tab_names))

        # Motor test must be removed per user request
        self.assertFalse(hasattr(self.widget, "motor_test_button"))
        self.assertFalse(hasattr(self.widget, "start_motor_test_button"))

    def test_connection_inputs_toggle(self):
        self.widget.combo_conn_type.setCurrentText("Serial")
        self.assertFalse(self.widget.serial_container.isHidden())
        self.assertTrue(self.widget.udp_container.isHidden())

        self.widget.combo_conn_type.setCurrentText("UDP")
        self.assertFalse(self.widget.udp_container.isHidden())
        self.assertTrue(self.widget.serial_container.isHidden())

    def test_hud_cards_exist(self):
        self.assertIsNotNone(self.widget.combo_flight_mode)
        self.assertIsNotNone(self.widget.btn_arm_toggle)
        self.assertIsNotNone(self.widget.lbl_roll_val)
        self.assertIsNotNone(self.widget.lbl_pitch_val)
        self.assertIsNotNone(self.widget.lbl_yaw_val)


if __name__ == "__main__":
    unittest.main()
