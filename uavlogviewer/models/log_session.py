"""
log_session.py — Session management for multiple loaded UAV flight logs.

Dependencies: PySide6, numpy, ParsedLog.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import numpy as np
from PySide6.QtCore import QObject, Signal

from uavlogviewer.parsers.base_parser import ParsedLog

MAX_LOGS = 8


def compute_t_first(parsed_log: ParsedLog) -> float:
    """Computes the earliest valid timestamp across all time series in a parsed log."""
    if not parsed_log or not parsed_log.timestamps:
        return 0.0

    min_t = None
    for arr in parsed_log.timestamps.values():
        if isinstance(arr, (list, np.ndarray)) and len(arr) > 0:
            first_val = float(arr[0])
            if np.isfinite(first_val):
                if min_t is None or first_val < min_t:
                    min_t = first_val

    return min_t if min_t is not None else 0.0


def compute_t_last(parsed_log: ParsedLog) -> float:
    """Computes the latest valid timestamp across all time series in a parsed log."""
    if not parsed_log or not parsed_log.timestamps:
        return 0.0

    max_t = None
    for arr in parsed_log.timestamps.values():
        if isinstance(arr, (list, np.ndarray)) and len(arr) > 0:
            last_val = float(arr[-1])
            if np.isfinite(last_val):
                if max_t is None or last_val > max_t:
                    max_t = last_val

    return max_t if max_t is not None else 0.0


@dataclass
class LoadedLog:
    log_id: int
    label: str  # e.g., "F1", "F2", ...
    filepath: str
    parsed: ParsedLog
    t_first: float
    user_offset: float = 0.0
    t_last: float = 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.t_last - self.t_first)


class LogSession(QObject):
    changed = Signal()
    active_changed = Signal(int)
    offsets_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logs: List[LoadedLog] = []
        self.active_log_id: Optional[int] = None
        self.zero_align_mode: str = "auto"  # "auto", "on", "off"
        self.flight_mode_source: str = "active"  # "active", "<log_id>", "none"
        self._next_id: int = 1

    @property
    def is_multi(self) -> bool:
        return len(self.logs) >= 2

    @property
    def active_log(self) -> Optional[LoadedLog]:
        if self.active_log_id is None:
            return self.logs[0] if self.logs else None
        for l in self.logs:
            if l.log_id == self.active_log_id:
                return l
        return self.logs[0] if self.logs else None

    @property
    def zero_align_enabled(self) -> bool:
        if self.zero_align_mode == "on":
            return True
        if self.zero_align_mode == "off":
            return False
        return self.is_multi

    def set_zero_align_mode(self, mode: str):
        if mode in ("auto", "on", "off") and mode != self.zero_align_mode:
            self.zero_align_mode = mode
            self.changed.emit()

    def set_flight_mode_source(self, src: str):
        if src != self.flight_mode_source:
            self.flight_mode_source = src
            self.changed.emit()

    def set_user_offset(self, log_id: int, offset: float):
        l = self.get(log_id)
        if l is not None and abs(l.user_offset - offset) > 1e-9:
            l.user_offset = float(offset)
            self.offsets_changed.emit()

    def reset_all_offsets(self):
        any_changed = False
        for l in self.logs:
            if abs(l.user_offset) > 1e-9:
                l.user_offset = 0.0
                any_changed = True
        if any_changed:
            self.offsets_changed.emit()

    def set_active(self, log_id: int):
        if self.active_log_id != log_id and any(l.log_id == log_id for l in self.logs):
            self.active_log_id = log_id
            self.active_changed.emit(log_id)
            self.changed.emit()

    def get(self, log_id: Optional[int]) -> Optional[LoadedLog]:
        if not self.logs:
            return None
        if log_id is None:
            return self.active_log
        for l in self.logs:
            if l.log_id == log_id:
                return l
        return self.active_log

    def _allocate_label(self) -> str:
        used_labels = {l.label for l in self.logs}
        for i in range(1, MAX_LOGS + 1):
            lbl = f"F{i}"
            if lbl not in used_labels:
                return lbl
        return f"F{len(self.logs) + 1}"

    def add_log(self, parsed: ParsedLog, filepath: str) -> Optional[LoadedLog]:
        if len(self.logs) >= MAX_LOGS:
            return None
        # Check duplicate file path
        if any(l.filepath == filepath for l in self.logs):
            return None

        log_id = self._next_id
        self._next_id += 1
        label = self._allocate_label()
        t_first = compute_t_first(parsed)

        loaded = LoadedLog(
            log_id=log_id,
            label=label,
            filepath=filepath,
            parsed=parsed,
            t_first=t_first,
            user_offset=0.0,
            t_last=compute_t_last(parsed)
        )
        self.logs.append(loaded)

        if self.active_log_id is None:
            self.active_log_id = log_id

        self.changed.emit()
        return loaded

    def remove_log(self, log_id: int):
        idx = -1
        for i, l in enumerate(self.logs):
            if l.log_id == log_id:
                idx = i
                break
        if idx >= 0:
            self.logs.pop(idx)
            if self.active_log_id == log_id:
                self.active_log_id = self.logs[0].log_id if self.logs else None
                if self.active_log_id is not None:
                    self.active_changed.emit(self.active_log_id)
            self.changed.emit()

    def clear(self):
        self.logs.clear()
        self.active_log_id = None
        self.changed.emit()

    def time_shift(self, log_id: Optional[int]) -> float:
        l = self.get(log_id)
        if not l:
            return 0.0
        base_shift = -l.t_first if self.zero_align_enabled else 0.0
        return float(base_shift + l.user_offset)

    def display_name(self, field: str, log_id: Optional[int]) -> str:
        if not self.is_multi:
            return field
        l = self.get(log_id)
        return f"[{l.label}] {field}" if l else field

    def flight_mode_log(self) -> Optional[LoadedLog]:
        if self.flight_mode_source == "none":
            return None
        if self.flight_mode_source == "active":
            return self.active_log
        try:
            target_id = int(self.flight_mode_source)
            return self.get(target_id)
        except ValueError:
            return self.active_log

    @staticmethod
    def from_parsed_log(parsed: ParsedLog, filepath: str = "") -> 'LogSession':
        session = LogSession()
        session.add_log(parsed, filepath or getattr(parsed, "filename", "log"))
        return session
