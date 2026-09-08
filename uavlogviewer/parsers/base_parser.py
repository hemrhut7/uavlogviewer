"""
base_parser.py — Base interface and data models for UAV log parsers.

Dependencies: numpy, dataclasses.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
import numpy as np

# Standard ArduPlane / QuadPlane flight mode mapping
PLANE_MODE_MAP = {
    0: "MANUAL",
    1: "CIRCLE",
    2: "STABILIZE",
    3: "TRAINING",
    4: "ACRO",
    5: "FBWA",
    6: "FBWB",
    7: "CRUISE",
    8: "AUTOTUNE",
    10: "AUTO",
    11: "RTL",
    12: "LOITER",
    13: "TAKEOFF",
    14: "AVOID_ADSB",
    15: "GUIDED",
    16: "INITIALISING",
    17: "QSTABILIZE",
    18: "QHOVER",
    19: "QLOITER",
    20: "QLAND",
    21: "QRTL",
    22: "QAUTOTUNE",
    23: "QACRO",
    24: "THERMAL"
}

# Standard ArduCopter flight mode mapping
COPTER_MODE_MAP = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    9: "LAND",
    11: "DRIFT",
    13: "SPORT",
    14: "FLIP",
    15: "AUTOTUNE",
    16: "POSHOLD",
    17: "BRAKE",
    18: "THROW",
    19: "AVOID_ADSB",
    20: "GUIDED_NOGPS",
    21: "SMART_RTL",
    22: "FLOWHOLD",
    23: "FOLLOW",
    24: "ZIGZAG",
    25: "SYSTEMID",
    26: "AUTOROTATE"
}

# High-contrast, distinctly different color palette for adjacent flight mode background shading
MODE_COLORS = {
    "MANUAL": "#64748B",      # Slate Gray
    "STABILIZE": "#EF4444",   # Bright Red
    "ALT_HOLD": "#3B82F6",    # Vivid Blue
    "AUTO": "#10B981",        # Emerald Green
    "RTL": "#F59E0B",         # Amber Orange
    "LOITER": "#8B5CF6",      # Purple
    "GUIDED": "#06B6D4",      # Cyan
    "LAND": "#EC4899",        # Pink
    "ACRO": "#EAB308",        # Yellow
    "FBWA": "#0284C7",        # Sky Blue
    "FBWB": "#D97706",        # Deep Amber
    "CRUISE": "#059669",      # Emerald
    "QSTABILIZE": "#F43F5E",  # Rose Red
    "QHOVER": "#2563EB",     # Royal Blue
    "QLOITER": "#10B981",     # Spring Green
    "QLAND": "#B45309",       # Dark Orange
    "QRTL": "#F59E0B",        # Bright Orange
    "THROW": "#EAB308",       # Yellow
    "POSHOLD": "#06B6D4"      # Cyan
}

HIGH_CONTRAST_PALETTE = [
    "#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
    "#EC4899", "#06B6D4", "#EAB308", "#6366F1", "#14B8A6"
]

def get_flight_mode_info(mode_val: Any, vehicle_type: str = "plane") -> Tuple[str, str]:
    """Returns (single_clean_mode_name, hex_color) for a given mode value."""
    mode_str = str(mode_val).strip()
    
    if mode_str.isdigit():
        mode_num = int(mode_str)
        if vehicle_type.lower() in ["copter", "acm"]:
            name = COPTER_MODE_MAP.get(mode_num, f"MODE_{mode_num}")
        else:
            name = PLANE_MODE_MAP.get(mode_num, f"MODE_{mode_num}")
    else:
        if "/" in mode_str:
            name = mode_str.split("/")[0].strip().upper()
        else:
            name = mode_str.upper()

    color = MODE_COLORS.get(name, None)
    if not color:
        color = HIGH_CONTRAST_PALETTE[abs(hash(name)) % len(HIGH_CONTRAST_PALETTE)]

    return name, color

@dataclass
class FlightModeSpan:
    name: str
    start_time: float
    end_time: float
    color: str = "#3B82F6"

@dataclass
class LogEvent:
    time: float
    name: str
    event_type: str = "INFO"

@dataclass
class SegmentInfo:
    index: int          # 0-indexed segment number
    start_idx: int      # First index (inclusive)
    end_idx: int        # Last index (inclusive)
    start_time: float   # Timestamp of first sample (in seconds)
    end_time: float     # Timestamp of last sample (in seconds)
    duration: float     # Duration in seconds
    samples: int        # Number of samples
    fs: float           # Estimated sampling rate (Hz)
    is_longest: bool = False

class LazyTimeSeriesDict(dict):
    """Dictionary that dynamically unpacks telemetry series from disk on-demand."""
    def __init__(self, parsed_log: Optional['ParsedLog'] = None, loader=None):
        super().__init__()
        self.parsed_log = parsed_log
        self.loader = loader
        self._loading = False

    def _trigger_load(self, key: str):
        if not self.loader or self._loading:
            return
        mtype = key.split('.')[0] if '.' in key else key
        base_mtype = mtype.split('[')[0]
        self._loading = True
        try:
            self.loader(base_mtype)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed lazy-unpacking msg_type %s: %s", base_mtype, e, exc_info=True)
        finally:
            self._loading = False

    def __getitem__(self, key: str) -> np.ndarray:
        if not super().__contains__(key):
            self._trigger_load(key)
        return super().__getitem__(key)

    def get(self, key: str, default=None):
        if not super().__contains__(key):
            self._trigger_load(key)
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        if super().__contains__(key):
            return True
        if isinstance(key, str) and self.parsed_log and self.parsed_log.field_tree:
            if '.' in key:
                mtype, f = key.split('.', 1)
                base_mtype = mtype.split('[')[0]
                if mtype in self.parsed_log.field_tree and f in self.parsed_log.field_tree[mtype]:
                    return True
                if base_mtype in self.parsed_log.field_tree and f in self.parsed_log.field_tree[base_mtype]:
                    return True
            elif "CALC" in self.parsed_log.field_tree and key in self.parsed_log.field_tree["CALC"]:
                return True
        return False

    def __len__(self) -> int:
        if not self.parsed_log or not self.parsed_log.field_tree:
            return super().__len__()
        count = sum(len(fields) for fields in self.parsed_log.field_tree.values())
        return max(super().__len__(), count)

    def __iter__(self):
        return iter(self.keys())

    def keys(self):
        if not self.parsed_log or not self.parsed_log.field_tree:
            return super().keys()
        all_k = set(super().keys())
        for mtype, fields in self.parsed_log.field_tree.items():
            for f in fields:
                all_k.add(f"{mtype}.{f}" if mtype != "CALC" else f)
        return all_k


class LazyTimestampsDict(dict):
    """Dictionary that dynamically unpacks telemetry timestamps from disk on-demand."""
    def __init__(self, parsed_log: Optional['ParsedLog'] = None, loader=None):
        super().__init__()
        self.parsed_log = parsed_log
        self.loader = loader
        self._loading = False

    def _trigger_load(self, key: str):
        if not self.loader or self._loading:
            return
        mtype = key.split('.')[0] if '.' in key else key
        base_mtype = mtype.split('[')[0]
        self._loading = True
        try:
            self.loader(base_mtype)
        except Exception:
            pass
        finally:
            self._loading = False

    def __getitem__(self, key: str) -> np.ndarray:
        if not super().__contains__(key):
            self._trigger_load(key)
        return super().__getitem__(key)

    def get(self, key: str, default=None):
        if not super().__contains__(key):
            self._trigger_load(key)
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        if super().__contains__(key):
            return True
        if isinstance(key, str) and self.parsed_log and self.parsed_log.field_tree:
            base_key = key.split('[')[0]
            if key in self.parsed_log.field_tree or base_key in self.parsed_log.field_tree:
                return True
        return False

    def __len__(self) -> int:
        if not self.parsed_log or not self.parsed_log.field_tree:
            return super().__len__()
        return max(super().__len__(), len(self.parsed_log.field_tree))

    def __iter__(self):
        return iter(self.keys())

    def keys(self):
        if not self.parsed_log or not self.parsed_log.field_tree:
            return super().keys()
        return set(super().keys()) | set(self.parsed_log.field_tree.keys())


@dataclass
class ParsedLog:
    filename: str = ""
    log_type: str = ""
    messages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    time_series: Dict[str, np.ndarray] = field(default_factory=dict)
    timestamps: Dict[str, np.ndarray] = field(default_factory=dict)
    flight_modes: List[FlightModeSpan] = field(default_factory=list)
    events: List[LogEvent] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    text_messages: List[Dict[str, Any]] = field(default_factory=list)
    field_tree: Dict[str, List[str]] = field(default_factory=dict)
    estimated_rates: Dict[str, float] = field(default_factory=dict)
    total_log_duration: float = 0.0

    def get_data_rate(self, msg_type: str) -> float:
        if msg_type in self.estimated_rates:
            return self.estimated_rates[msg_type]
        clean_type = msg_type.split('.')[0]
        if clean_type in self.estimated_rates:
            return self.estimated_rates[clean_type]
        base_mtype = clean_type.split('[')[0]
        if base_mtype in self.estimated_rates:
            return self.estimated_rates[base_mtype]
        t_arr = self.timestamps.get(clean_type, self.timestamps.get(msg_type))
        return calculate_data_rate(t_arr)

    def get_segments(self, msg_type_or_field: str = "") -> List[SegmentInfo]:
        """Gets continuous segments for a given msg_type or field, or primary telemetry timestamps."""
        if not self.timestamps and not self.field_tree:
            return []
        
        target_type = msg_type_or_field
        if target_type and target_type in self.timestamps:
            t_arr = self.timestamps[target_type]
        elif target_type and '.' in target_type and target_type.split('.')[0] in self.timestamps:
            t_arr = self.timestamps[target_type.split('.')[0]]
        else:
            primary_key = None
            candidates = (
                "ATT", "ATT[0]", "POS", "POS[0]", "GPS", "GPS[0]", "BARO", "BARO[0]", "IMU", "IMU[0]",
                "CTUN", "NTUN", "STAT", "ATTITUDE", "RAW_IMU", "HIGHRES_IMU", "GLOBAL_POSITION_INT", "VFR_HUD",
                "SERVO_OUTPUT_RAW", "GPS_RAW_INT", "SCALED_IMU", "SYS_STATUS"
            )
            for candidate in candidates:
                if candidate in self.timestamps and len(self.timestamps[candidate]) > 0:
                    primary_key = candidate
                    break
            if not primary_key:
                best_len = -1
                for k, v in self.timestamps.items():
                    if len(v) > best_len:
                        best_len = len(v)
                        primary_key = k
            t_arr = self.timestamps.get(primary_key, np.array([]))
            
        return detect_segments_from_timestamps(t_arr)

def detect_segments_from_timestamps(
    timestamps: np.ndarray,
    gap_multiplier: float = 20.0,
    min_gap_s: float = 15.0,
    min_seg_samples: int = 5
) -> List[SegmentInfo]:
    """Detects continuous time-series segments separated by gaps in a 1D timestamps array (in seconds)."""
    if timestamps is None or len(timestamps) == 0:
        return []

    t_arr = np.array(timestamps, dtype=np.float64)

    if len(t_arr) < 2:
        t0 = float(t_arr[0]) if len(t_arr) == 1 else 0.0
        return [SegmentInfo(
            index=0, start_idx=0, end_idx=len(t_arr) - 1 if len(t_arr) > 0 else 0,
            start_time=t0, end_time=t0, duration=0.0, samples=len(t_arr),
            fs=0.0, is_longest=True
        )]

    diffs = np.diff(t_arr)
    positive = diffs[diffs > 0]

    if len(positive) == 0:
        t0, t1 = float(t_arr[0]), float(t_arr[-1])
        return [SegmentInfo(
            index=0, start_idx=0, end_idx=len(t_arr) - 1,
            start_time=t0, end_time=t1, duration=max(0.0, t1 - t0),
            samples=len(t_arr), fs=0.0, is_longest=True
        )]

    median_dt = float(np.median(positive))
    gap_threshold = max(median_dt * gap_multiplier, min_gap_s)

    raw_gap_indices = np.flatnonzero(diffs > gap_threshold)
    filtered_gap_indices = [g_idx for g_idx in raw_gap_indices if diffs[g_idx] >= min_gap_s]

    gap_indices = np.array(filtered_gap_indices, dtype=np.int64)
    starts = np.r_[0, gap_indices + 1] if len(gap_indices) > 0 else np.array([0])
    ends = np.r_[gap_indices, len(t_arr) - 1] if len(gap_indices) > 0 else np.array([len(t_arr) - 1])

    raw_segments: List[SegmentInfo] = []
    for (s, e) in zip(starts, ends):
        s_int, e_int = int(s), int(e)
        seg_time = t_arr[s_int : e_int + 1]
        n = len(seg_time)
        t0, t1 = float(seg_time[0]), float(seg_time[-1])
        dur_s = max(0.0, t1 - t0)

        if dur_s > 0 and n > 1:
            fs = (n - 1) / dur_s
        else:
            fs = 0.0

        raw_segments.append(SegmentInfo(
            index=0,
            start_idx=s_int,
            end_idx=e_int,
            start_time=t0,
            end_time=t1,
            duration=dur_s,
            samples=n,
            fs=fs,
            is_longest=False
        ))

    # Filter out micro noise segments if larger segments exist
    valid_segments = [s for s in raw_segments if s.samples >= min_seg_samples or s.duration >= 1.0]
    if not valid_segments:
        valid_segments = raw_segments

    longest_idx = 0
    max_duration = -1.0
    max_samples = -1
    final_segments: List[SegmentInfo] = []

    for seg_idx, seg in enumerate(valid_segments):
        if seg.duration > max_duration or (seg.duration == max_duration and seg.samples > max_samples):
            max_duration = seg.duration
            max_samples = seg.samples
            longest_idx = seg_idx

        final_segments.append(SegmentInfo(
            index=seg_idx,
            start_idx=seg.start_idx,
            end_idx=seg.end_idx,
            start_time=seg.start_time,
            end_time=seg.end_time,
            duration=seg.duration,
            samples=seg.samples,
            fs=seg.fs,
            is_longest=False
        ))

    if final_segments:
        final_segments[longest_idx] = SegmentInfo(
            index=final_segments[longest_idx].index,
            start_idx=final_segments[longest_idx].start_idx,
            end_idx=final_segments[longest_idx].end_idx,
            start_time=final_segments[longest_idx].start_time,
            end_time=final_segments[longest_idx].end_time,
            duration=final_segments[longest_idx].duration,
            samples=final_segments[longest_idx].samples,
            fs=final_segments[longest_idx].fs,
            is_longest=True
        )

    return final_segments


def calculate_data_rate(timestamps: np.ndarray) -> float:
    """Calculates effective data rate (Hz) for a series of timestamps, robust to long time gaps."""
    if timestamps is None or len(timestamps) < 2:
        return 0.0
    
    dt = np.diff(timestamps)
    dt = dt[dt > 0]
    if len(dt) == 0:
        return 0.0
    
    med_dt = float(np.median(dt))
    if med_dt <= 0:
        return 0.0
    
    # Exclude gaps longer than 3.0s or 5 * median(dt) to handle long pause breakpoints
    gap_threshold = max(3.0, 5.0 * med_dt)
    active_dt = dt[dt <= gap_threshold]
    
    if len(active_dt) > 0:
        mean_dt = float(np.mean(active_dt))
        return 1.0 / mean_dt if mean_dt > 0 else 0.0
    else:
        return 1.0 / med_dt

def format_data_rate(rate: float) -> str:
    """Formats data rate into a human-readable string."""
    if rate <= 0:
        return "0 Hz"
    elif rate >= 100:
        return f"{rate:.0f} Hz"
    elif rate >= 10:
        return f"{rate:.1f} Hz"
    elif rate >= 1:
        return f"{rate:.1f} Hz"
    else:
        return f"{rate:.2f} Hz"

# Messages that are explicitly known to use sensor/core/hardware instance indexing
INSTANCE_MESSAGE_TYPES = {
    'XKF1', 'XKF2', 'XKF3', 'XKF4', 'XKQ1', 'XKQ2', 'XKQ',
    'NKF1', 'NKF2', 'NKF3', 'NKF4', 'NKQ1', 'NKQ2', 'NKQ',
    'IMU', 'ACC', 'GYR', 'BARO', 'MAG', 'GPS', 'POS', 'GPA',
    'RFND', 'BAT', 'BAT2', 'ESC', 'ORGN', 'AHR2', 'RATE',
    'RAW_IMU', 'SCALED_IMU', 'SCALED_IMU2', 'SCALED_IMU3',
    'BATTERY_STATUS', 'DISTANCE_SENSOR', 'MCU_STATUS'
}

# Messages that must NEVER be split by instance (PID integrators, units, system messages, etc.)
EXCLUDE_INSTANCE_TYPES = {
    'PARM', 'FMT', 'FMTU', 'UNIT', 'MSG', 'EV', 'MODE', 'HEAT',
    'PIDR', 'PIDP', 'PIDY', 'PIDA', 'PIDZ', 'PIDS', 'TECS', 'TECB',
    'PSCD', 'PSCE', 'PSCN', 'STAT', 'STATUSTEXT', 'HEARTBEAT'
}

def is_valid_instance_column(mtype: str, col_name: str, values: Any) -> bool:
    """Strict check to prevent misidentifying PID integrals (I), Heat (I), or unit IDs as instance columns."""
    base_mtype = mtype.split('[')[0].upper()
    if base_mtype in EXCLUDE_INSTANCE_TYPES or base_mtype.startswith('PID'):
        return False
    
    if values is None or len(values) == 0:
        return False

    if col_name not in ('C', 'I', 'Instance', 'instance', 'Inst', 'Core', 'Id', 'ID', 'id', 'sensor_id'):
        return False
        
    unique_vals = np.unique(values)
    if len(unique_vals) == 0 or len(unique_vals) > 32:
        return False

    try:
        float_vals = unique_vals.astype(np.float64)
        if np.any(np.isnan(float_vals)):
            return False
        # All values must be integer-like (e.g. 0, 1, 100) and within uint8 byte range (0 to 255)
        if not np.all(np.abs(float_vals - np.round(float_vals)) < 1e-4):
            return False
        if not np.all((float_vals >= 0) & (float_vals <= 255)):
            return False
    except (ValueError, TypeError):
        return False

    if len(unique_vals) == 1 and base_mtype not in INSTANCE_MESSAGE_TYPES:
        return False

    return True

class BaseParser:
    def parse(self, filepath: str) -> ParsedLog:
        raise NotImplementedError("Subclasses must implement parse()")


