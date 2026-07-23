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

class BaseParser:
    def parse(self, filepath: str) -> ParsedLog:
        raise NotImplementedError("Subclasses must implement parse()")
