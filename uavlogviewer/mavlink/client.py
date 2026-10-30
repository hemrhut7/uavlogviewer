"""
client.py — MAVLink Client handling UDP/Serial connection, message dispatching,
flight mode detection, actuator controls and parameter caching.
"""
import os
import re
import time
import threading
from math import degrees, nan
from typing import Callable, Dict, List, Optional, Set, Tuple

os.environ['MAVLINK20'] = '1'

import serial
import serial.tools.list_ports
from pymavlink import mavutil
from PySide6.QtCore import QObject, Signal


def natural_sort_key(s: str):
    """Sort strings with embedded numbers naturally (e.g. ACM0, ACM1, ACM2, ACM10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def get_serial_ports() -> List[str]:
    """Scans and returns available serial ports, excluding /dev/ttyS* system serial ports."""
    try:
        ports = serial.tools.list_ports.comports()
        filtered = [p.device for p in ports if not p.device.startswith("/dev/ttyS")]
        filtered.sort(key=natural_sort_key)
        return filtered
    except Exception as e:
        print(f"get_serial_ports error: {e}")
        return []


class MavlinkClient(QObject):
    connection_changed = Signal(bool, str)
    statustext_received = Signal(str)
    param_received = Signal(str, float)
    params_updated = Signal(dict)

    # ArduCopter flight mode mapping
    COPTER_MODES = {
        0: 'STABILIZE', 1: 'ACRO', 2: 'ALT_HOLD', 3: 'AUTO', 4: 'GUIDED',
        5: 'LOITER', 6: 'RTL', 7: 'CIRCLE', 8: 'LAND', 10: 'DRIFT',
        11: 'SPORT', 13: 'FLIP', 14: 'AUTOTUNE', 15: 'POSHOLD', 16: 'BRAKE',
        17: 'THROW', 18: 'AVOID_ADSB', 19: 'GUIDED_NOGPS', 20: 'SMART_RTL',
        21: 'FLOWHOLD', 22: 'FOLLOW', 23: 'ZIGZAG', 24: 'SYSTEMID', 25: 'AUTOROTATE',
        26: 'AUTO_RTL',
    }

    # ArduPlane (including VTOL / QuadPlane Q-Modes) flight mode mapping
    PLANE_MODES = {
        0: 'MANUAL', 1: 'CIRCLE', 2: 'STABILIZE', 3: 'TRAINING', 4: 'ACRO',
        5: 'FBWA', 6: 'FBWB', 7: 'CRUISE', 8: 'AUTOTUNE', 10: 'AUTO',
        11: 'RTL', 12: 'LOITER', 13: 'TAKEOFF', 14: 'AVOID_ADSB', 15: 'GUIDED',
        16: 'INITIALIZING', 17: 'QSTABILIZE', 18: 'QHOVER', 19: 'QLOITER',
        20: 'QLAND', 21: 'QRTL', 22: 'QAUTOTUNE', 23: 'QACRO', 24: 'THERMAL',
        25: 'LOITER_ALT_QLAND'
    }

    GNSS_FIX_TYPES = {
        0: "NO_GPS", 1: "NO_FIX", 2: "2D_FIX", 3: "3D_FIX", 4: "DGPS",
        5: "RTK_FLOAT", 6: "RTK_FIXED", 7: "STATIC", 8: "PPP"
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.master = None
        self.is_running = False
        self.read_thread: Optional[threading.Thread] = None

        self.target_system: Optional[int] = None
        self.target_component: Optional[int] = None

        self._source_messages: Dict[Tuple[int, int], Dict[str, dict]] = {}
        self._last_msg_content: Dict[str, dict] = {}
        self.parameters: Dict[str, float] = {}

        self.error_msg: str = ""
        self._message_callbacks: List[Callable] = []

    def get_mav_master(self):
        return self.master

    def is_connected(self) -> bool:
        return self.master is not None and self.is_running

    def connect_udp(self, ip: str = "0.0.0.0", port: int = 14550, con_type: str = "in", timeout: float = 8.0) -> bool:
        self.disconnect()
        try:
            device_str = f"udpin:{ip}:{port}" if con_type == "in" else f"udpout:{ip}:{port}"
            self.master = mavutil.mavlink_connection(device_str, source_component=77)
            if self.master.wait_heartbeat(blocking=True, timeout=timeout):
                if self.target_system is None:
                    self.target_system = self.master.target_system
                    self.target_component = self.master.target_component or 1
                self._start_reading()
                self.connection_changed.emit(True, f"UDP {ip}:{port}")
                return True
            else:
                self.error_msg = f"Timeout waiting for heartbeat on {device_str}"
                self.disconnect()
                return False
        except Exception as e:
            self.error_msg = f"UDP connect error: {e}"
            self.disconnect()
            return False

    def connect_serial(self, port: str, baud: int = 115200, timeout: float = 8.0) -> bool:
        self.disconnect()
        try:
            self.master = mavutil.mavlink_connection(port, baud=baud, source_component=77)
            if self.master.wait_heartbeat(blocking=True, timeout=timeout):
                if self.target_system is None:
                    self.target_system = self.master.target_system
                    self.target_component = self.master.target_component or 1
                self._start_reading()
                self.connection_changed.emit(True, f"Serial {port} @ {baud}")
                return True
            else:
                self.error_msg = f"Timeout waiting for heartbeat on {port}"
                self.disconnect()
                return False
        except Exception as e:
            self.error_msg = f"Serial connect error: {e}"
            self.disconnect()
            return False

    def disconnect(self):
        self.is_running = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=0.2)
        if self.master:
            try:
                self.master.close()
            except Exception:
                pass
            self.master = None
        self.connection_changed.emit(False, "")

    def _start_reading(self):
        self.is_running = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()

    def _read_loop(self):
        while self.is_running and self.master:
            try:
                msg = self.master.recv_match(blocking=False)
                if msg:
                    self._process_mavlink_message(msg)
                else:
                    time.sleep(0.001)
            except Exception as e:
                if self.is_running:
                    print(f"Mavlink read error: {e}")
                break

    def _process_mavlink_message(self, msg):
        if not msg:
            return

        msg_type = msg.get_type()
        sys_id = msg.get_srcSystem()
        comp_id = msg.get_srcComponent()

        # Handle STATUSTEXT
        if msg_type == "STATUSTEXT":
            text = getattr(msg, 'text', '')
            self.statustext_received.emit(text)

        # Filter out GCS sys_id 0 and 255 from vehicle source list
        if sys_id in (0, 255):
            return

        src = (sys_id, comp_id)
        if src not in self._source_messages:
            self._source_messages[src] = {}
        if msg_type not in self._source_messages[src]:
            self._source_messages[src][msg_type] = {'count': 0, 'temp_count': 0, 'content': {}}

        msg_dict = msg.to_dict()
        self._source_messages[src][msg_type]['count'] += 1
        self._source_messages[src][msg_type]['temp_count'] += 1
        self._source_messages[src][msg_type]['content'] = msg_dict
        self._last_msg_content[msg_type] = msg_dict

        if self.target_system is None:
            self.target_system = sys_id
            self.target_component = comp_id

        # Parameter value
        if msg_type == "PARAM_VALUE":
            p_id = getattr(msg, 'param_id', '')
            if isinstance(p_id, bytes):
                p_id = p_id.decode('utf-8', errors='ignore').rstrip('\x00')
            p_val = float(getattr(msg, 'param_value', 0.0))
            self.parameters[p_id] = p_val
            self.param_received.emit(p_id, p_val)
            param_index = getattr(msg, 'param_index', 0)
            param_count = getattr(msg, 'param_count', 0)
            if param_index == param_count - 1 or param_count == 0:
                self.params_updated.emit(self.parameters.copy())

        # Notify registered callbacks (e.g. data buffer)
        for cb in self._message_callbacks:
            try:
                cb(msg)
            except Exception:
                pass

    def add_message_callback(self, cb: Callable):
        if cb not in self._message_callbacks:
            self._message_callbacks.append(cb)

    def remove_message_callback(self, cb: Callable):
        if cb in self._message_callbacks:
            self._message_callbacks.remove(cb)

    def get_detected_systems(self) -> List[Tuple[int, int]]:
        return sorted(list(self._source_messages.keys()))

    def set_target_system(self, sys_id: int, comp_id: Optional[int] = None):
        self.target_system = sys_id
        self.target_component = comp_id if comp_id is not None else 1

    def get_source_message_counts(self) -> Dict[Tuple[int, int], Dict[str, int]]:
        """Returns message arrival rate (counts since last call) per source."""
        result = {}
        for src, msgs in self._source_messages.items():
            result[src] = {}
            for m_type, data in msgs.items():
                result[src][m_type] = data['temp_count']
                data['temp_count'] = 0
        return result

    def get_source_message_content(self, sys_id: int, comp_id: int, msg_type: str) -> dict:
        return self._source_messages.get((sys_id, comp_id), {}).get(msg_type, {}).get('content', {})

    def get_source_total_message_count(self, sys_id: int, comp_id: int, msg_type: str) -> int:
        return self._source_messages.get((sys_id, comp_id), {}).get(msg_type, {}).get('count', 0)

    def get_last_msg_content(self, msg_type: str) -> dict:
        if self.target_system is not None and self.target_component is not None:
            return self.get_source_message_content(self.target_system, self.target_component, msg_type)
        return self._last_msg_content.get(msg_type, {})

    # Flight status getters
    def get_flight_mode(self) -> str:
        hb = self.get_last_msg_content("HEARTBEAT")
        if hb:
            custom_mode = hb.get('custom_mode', -1)
            v_type = hb.get('type', -1)
            if v_type == 1 or (19 <= v_type <= 25):  # Fixed wing / VTOL
                return self.PLANE_MODES.get(custom_mode, f"Plane({custom_mode})")
            elif v_type in [2, 13, 14, 15]:  # Copter
                return self.COPTER_MODES.get(custom_mode, f"Copter({custom_mode})")
            return self.PLANE_MODES.get(custom_mode, f"Unknown({custom_mode})")
        return "N/A"

    def get_mode_list(self) -> List[str]:
        hb = self.get_last_msg_content("HEARTBEAT")
        if hb:
            v_type = hb.get('type', -1)
            if v_type in [2, 13, 14, 15]:
                return sorted(list(self.COPTER_MODES.values()))
        return sorted(list(self.PLANE_MODES.values()))

    def is_armed(self) -> bool:
        hb = self.get_last_msg_content("HEARTBEAT")
        if hb:
            base_mode = hb.get('base_mode', 0)
            return bool(base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        return False

    def get_gnss_fix_type(self) -> str:
        gps = self.get_last_msg_content("GPS_RAW_INT")
        if gps:
            fix = gps.get('fix_type', -1)
            return self.GNSS_FIX_TYPES.get(fix, f"Unknown({fix})")
        return "No Fix"

    def get_gnss_sats(self) -> int:
        gps = self.get_last_msg_content("GPS_RAW_INT")
        return gps.get('satellites_visible', 0) if gps else 0

    # Actuator & Command Controls
    def set_flight_mode(self, mode_name: str):
        if not self.master:
            return
        hb = self.get_last_msg_content("HEARTBEAT")
        v_type = hb.get('type', -1)
        is_copter = v_type in [2, 13, 14, 15]
        mode_dict = self.COPTER_MODES if is_copter else self.PLANE_MODES

        mode_id = next((k for k, v in mode_dict.items() if v == mode_name), None)
        if mode_id is not None:
            self.send_command_long(mavutil.mavlink.MAV_CMD_DO_SET_MODE, 1, mode_id, 0, 0, 0, 0, 0)

    def arm_disarm(self, arm: bool, force: bool = False):
        val = 1 if arm else 0
        force_val = 21196 if force else 0
        self.send_command_long(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, val, force_val, 0, 0, 0, 0, 0)

    def send_engine_start_command(self, start_control: int, cold_start: int = 0, height_delay: float = 0.0, flags: int = 0):
        self.send_command_long(
            mavutil.mavlink.MAV_CMD_DO_ENGINE_CONTROL,
            start_control, cold_start, height_delay, 0, 0, 0, flags
        )

    def send_command_long(self, command_id: int, p1: float = 0, p2: float = 0, p3: float = 0, p4: float = 0, p5: float = 0, p6: float = 0, p7: float = 0):
        if self.master:
            sys_id = self.target_system if self.target_system is not None else self.master.target_system
            comp_id = self.target_component if self.target_component is not None else (self.master.target_component or 1)
            self.master.mav.command_long_send(
                sys_id, comp_id,
                command_id,
                0,
                float(p1), float(p2), float(p3), float(p4), float(p5), float(p6), float(p7)
            )

    def override_rc_channels(self, channels: List[int], vals: List[int]):
        if not self.master or len(channels) != len(vals):
            return
        ch_list = [0] * 18
        for ch, v in zip(channels, vals):
            if 1 <= ch <= 18:
                ch_list[ch - 1] = int(v)
        sys_id = self.target_system if self.target_system is not None else self.master.target_system
        comp_id = self.target_component if self.target_component is not None else (self.master.target_component or 1)
        self.master.mav.rc_channels_override_send(sys_id, comp_id, *ch_list)

    def reboot(self):
        self.send_command_long(mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 1, 0, 0, 0, 0, 0, 0)

    # Parameters
    def request_all_params(self):
        if self.master:
            self.parameters.clear()
            sys_id = self.target_system if self.target_system is not None else self.master.target_system
            comp_id = self.target_component if self.target_component is not None else (self.master.target_component or 1)
            self.master.mav.param_request_list_send(sys_id, comp_id)

    def set_param(self, param_id: str, param_value: float):
        if self.master:
            sys_id = self.target_system if self.target_system is not None else self.master.target_system
            comp_id = self.target_component if self.target_component is not None else (self.master.target_component or 1)
            p_id = param_id.encode('utf-8') if isinstance(param_id, str) else param_id
            self.master.mav.param_set_send(
                sys_id, comp_id,
                p_id,
                float(param_value),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32
            )

    def get_parameters(self) -> Dict[str, float]:
        return self.parameters.copy()

    def save_parameters_to_file(self, filename: str) -> bool:
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for p_id in sorted(self.parameters.keys()):
                    val = self.parameters[p_id]
                    if isinstance(val, float) and val.is_integer():
                        val = int(val)
                    f.write(f"{p_id},{val}\n")
            return True
        except Exception as e:
            print(f"Failed to save parameters: {e}")
            return False
