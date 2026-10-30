"""
data_buffer.py — High-performance, thread-safe rolling buffer for real-time MAVLink telemetry fields.
"""
import time
from collections import deque
from typing import Dict, List, Set, Tuple
import numpy as np
from PySide6.QtCore import QMutex, QMutexLocker


def format_field_label(key: Tuple[int, int, str, str]) -> str:
    """Format (sys_id, comp_id, msg_type, field) into a concise display label."""
    sys_id, comp_id, msg_type, field = key
    return f"{msg_type}.{field} (Sys:{sys_id})"


class MavlinkDataBuffer:
    """
    High-performance, thread-safe rolling buffer for selected MAVLink fields.
    Maintains timestamp and value deques for each tracked field.
    """
    def __init__(self, duration: float = 30.0):
        self._duration = float(duration)
        self._mutex = QMutex()
        self._selected_fields: Set[Tuple[int, int, str, str]] = set()
        self._active_msg_keys: Dict[Tuple[int, int, str], List[str]] = {}
        # key -> (deque of timestamps, deque of values)
        self._data: Dict[Tuple[int, int, str, str], Tuple[deque, deque]] = {}

    def set_duration(self, duration: float):
        with QMutexLocker(self._mutex):
            self._duration = max(1.0, float(duration))

    def get_duration(self) -> float:
        with QMutexLocker(self._mutex):
            return self._duration

    def set_selected_fields(self, fields: Set[Tuple[int, int, str, str]]):
        with QMutexLocker(self._mutex):
            self._selected_fields = set(fields)
            self._active_msg_keys = {}
            for key in self._selected_fields:
                sys_id, comp_id, msg_type, field = key
                msg_key = (sys_id, comp_id, msg_type)
                if msg_key not in self._active_msg_keys:
                    self._active_msg_keys[msg_key] = []
                self._active_msg_keys[msg_key].append(field)
                if key not in self._data:
                    self._data[key] = (deque(), deque())

            # Remove keys that are no longer selected
            for key in list(self._data.keys()):
                if key not in self._selected_fields:
                    del self._data[key]

    def clear_data(self):
        with QMutexLocker(self._mutex):
            for ts_dq, val_dq in self._data.values():
                ts_dq.clear()
                val_dq.clear()

    def on_mavlink_message(self, msg):
        """
        Fast callback executed for incoming MAVLink messages.
        Filters by active message keys and appends numeric field values.
        """
        if not self._active_msg_keys:
            return

        try:
            sys_id = msg.get_srcSystem()
            comp_id = msg.get_srcComponent()
            msg_type = msg.get_type()
        except Exception:
            return

        msg_key = (sys_id, comp_id, msg_type)
        fields = self._active_msg_keys.get(msg_key)
        if not fields:
            return

        try:
            msg_dict = msg.to_dict()
        except Exception:
            return

        now = time.time()
        with QMutexLocker(self._mutex):
            cutoff = now - self._duration
            for f in fields:
                val = msg_dict.get(f)
                if val is not None and isinstance(val, (int, float)) and not isinstance(val, bool):
                    key = (sys_id, comp_id, msg_type, f)
                    if key in self._data:
                        ts_dq, val_dq = self._data[key]
                        ts_dq.append(now)
                        val_dq.append(float(val))
                        while ts_dq and ts_dq[0] < cutoff:
                            ts_dq.popleft()
                            val_dq.popleft()

    def get_field_data(self, key: Tuple[int, int, str, str]) -> Tuple[np.ndarray, np.ndarray]:
        with QMutexLocker(self._mutex):
            if key not in self._data or not self._data[key][0]:
                return np.empty(0, dtype=float), np.empty(0, dtype=float)
            ts_dq, val_dq = self._data[key]
            return np.fromiter(ts_dq, dtype=float), np.fromiter(val_dq, dtype=float)

    def get_active_fields(self) -> Set[Tuple[int, int, str, str]]:
        with QMutexLocker(self._mutex):
            return set(self._selected_fields)
