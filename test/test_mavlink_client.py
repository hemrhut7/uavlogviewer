import unittest
from unittest.mock import MagicMock, patch
from uavlogviewer.mavlink.client import MavlinkClient, get_serial_ports, natural_sort_key


class FakeSerialPort:
    def __init__(self, device):
        self.device = device


class TestMavlinkClient(unittest.TestCase):
    def test_natural_sort_ports(self):
        ports = [
            FakeSerialPort("/dev/ttyACM10"),
            FakeSerialPort("/dev/ttyACM2"),
            FakeSerialPort("/dev/ttyS0"),  # Should be filtered out
            FakeSerialPort("/dev/ttyACM1"),
            FakeSerialPort("/dev/ttyACM0"),
        ]
        with patch("serial.tools.list_ports.comports", return_value=ports):
            sorted_ports = get_serial_ports()
            self.assertEqual(sorted_ports, ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyACM2", "/dev/ttyACM10"])

    def test_client_init_and_target_system(self):
        client = MavlinkClient()
        self.assertFalse(client.is_connected())
        self.assertEqual(client.get_detected_systems(), [])

        client.set_target_system(1, 1)
        self.assertEqual(client.target_system, 1)
        self.assertEqual(client.target_component, 1)

    def test_process_message_accounting(self):
        client = MavlinkClient()
        client.set_target_system(1, 1)

        msg = MagicMock()
        msg.get_type.return_value = "ATTITUDE"
        msg.get_srcSystem.return_value = 1
        msg.get_srcComponent.return_value = 1
        msg.to_dict.return_value = {"roll": 0.1, "pitch": -0.2, "yaw": 1.5}

        client._process_mavlink_message(msg)

        self.assertIn((1, 1), client.get_detected_systems())
        counts = client.get_source_message_counts()
        self.assertEqual(counts[(1, 1)]["ATTITUDE"], 1)
        content = client.get_source_message_content(1, 1, "ATTITUDE")
        self.assertEqual(content["roll"], 0.1)

    def test_flight_mode_resolution(self):
        client = MavlinkClient()
        client.set_target_system(1, 1)

        # Heartbeat message for Plane FBWA (mode 5, type 1: FIXED_WING)
        msg = MagicMock()
        msg.get_type.return_value = "HEARTBEAT"
        msg.get_srcSystem.return_value = 1
        msg.get_srcComponent.return_value = 1
        msg.to_dict.return_value = {"custom_mode": 5, "type": 1, "base_mode": 128}

        client._process_mavlink_message(msg)

        self.assertEqual(client.get_flight_mode(), "FBWA")
        self.assertTrue(client.is_armed())


if __name__ == "__main__":
    unittest.main()
