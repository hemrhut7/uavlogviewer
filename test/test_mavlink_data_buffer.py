import unittest
import time
from uavlogviewer.mavlink.data_buffer import MavlinkDataBuffer


class FakeMessage:
    def __init__(self, sys_id, comp_id, msg_type, data):
        self._sys = sys_id
        self._comp = comp_id
        self._type = msg_type
        self._data = data

    def get_srcSystem(self):
        return self._sys

    def get_srcComponent(self):
        return self._comp

    def get_type(self):
        return self._type

    def to_dict(self):
        return self._data


class TestMavlinkDataBuffer(unittest.TestCase):
    def setUp(self):
        self.buffer = MavlinkDataBuffer(duration=10.0)

    def test_duration_control(self):
        self.assertEqual(self.buffer.get_duration(), 10.0)
        self.buffer.set_duration(60.0)
        self.assertEqual(self.buffer.get_duration(), 60.0)

    def test_field_selection_and_ingestion(self):
        f1 = (1, 1, "ATTITUDE", "roll")
        f2 = (1, 1, "VFR_HUD", "airspeed")
        self.buffer.set_selected_fields({f1, f2})

        msg1 = FakeMessage(1, 1, "ATTITUDE", {"roll": 1.25, "pitch": -0.5})
        msg2 = FakeMessage(1, 1, "VFR_HUD", {"airspeed": 22.4})
        msg3 = FakeMessage(1, 1, "RAW_IMU", {"xacc": 100})

        self.buffer.on_mavlink_message(msg1)
        self.buffer.on_mavlink_message(msg2)
        self.buffer.on_mavlink_message(msg3)

        ts1, vs1 = self.buffer.get_field_data(f1)
        ts2, vs2 = self.buffer.get_field_data(f2)

        self.assertEqual(len(vs1), 1)
        self.assertAlmostEqual(vs1[0], 1.25)
        self.assertEqual(len(vs2), 1)
        self.assertAlmostEqual(vs2[0], 22.4)

    def test_clear_data(self):
        f1 = (1, 1, "ATTITUDE", "yaw")
        self.buffer.set_selected_fields({f1})
        self.buffer.on_mavlink_message(FakeMessage(1, 1, "ATTITUDE", {"yaw": 180.0}))

        ts, vs = self.buffer.get_field_data(f1)
        self.assertEqual(len(vs), 1)

        self.buffer.clear_data()
        ts, vs = self.buffer.get_field_data(f1)
        self.assertEqual(len(vs), 0)


if __name__ == "__main__":
    unittest.main()
