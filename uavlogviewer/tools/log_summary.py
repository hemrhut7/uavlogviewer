"""
log_summary.py — Analyzes ParsedLog for key summary statistics (flight time, wind speed).

Supports both DataFlash binary (.bin/.log) and MAVLink telemetry (.tlog) log formats.

Dependencies: numpy, dataclasses, uavlogviewer.parsers.base_parser.

Typical usage::

    from uavlogviewer.tools.log_summary import analyze_log_summary
    summary = analyze_log_summary(parsed_log)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np
from uavlogviewer.parsers.base_parser import ParsedLog


@dataclass
class FlightSpan:
    start_time: float
    end_time: float
    duration: float  # seconds

    def format_duration(self) -> str:
        d = int(round(self.duration))
        hrs = d // 3600
        mins = (d % 3600) // 60
        secs = d % 60
        if hrs > 0:
            return f"{hrs}h {mins}m {secs}s ({self.duration:.1f} s)"
        elif mins > 0:
            return f"{mins}m {secs}s ({self.duration:.1f} s)"
        else:
            return f"{secs}s ({self.duration:.1f} s)"


@dataclass
class LogSummary:
    filename: str = ""
    log_type: str = ""
    total_log_duration: float = 0.0
    
    # Arming / Flight Time
    has_arming_data: bool = False
    arming_source: str = ""
    flight_spans: List[FlightSpan] = field(default_factory=list)
    longest_flight_span: Optional[FlightSpan] = None
    flight_count: int = 0
    total_armed_duration: float = 0.0
    
    # Wind Speed
    has_wind_data: bool = False
    wind_source: str = ""
    avg_wind_speed_ms: Optional[float] = None
    max_wind_speed_ms: Optional[float] = None

    def get_formatted_flight_time(self) -> str:
        if self.longest_flight_span and self.longest_flight_span.duration > 0:
            dur_str = self.longest_flight_span.format_duration()
            if self.flight_count > 1:
                return f"{dur_str} (Longest of {self.flight_count} flights)"
            return dur_str
        elif self.total_log_duration > 0:
            d = int(round(self.total_log_duration))
            mins = d // 60
            secs = d % 60
            return f"{mins}m {secs}s ({self.total_log_duration:.1f} s) [Full Log]"
        return "N/A"

    def get_formatted_wind_speed(self) -> str:
        if self.has_wind_data and self.avg_wind_speed_ms is not None and self.max_wind_speed_ms is not None:
            avg_kmh = self.avg_wind_speed_ms * 3.6
            max_kmh = self.max_wind_speed_ms * 3.6
            return f"Avg: {self.avg_wind_speed_ms:.1f} m/s ({avg_kmh:.1f} km/h) | Max: {self.max_wind_speed_ms:.1f} m/s ({max_kmh:.1f} km/h)"
        return "N/A (No wind data)"


def extract_flight_spans(parsed: ParsedLog) -> Tuple[bool, List[FlightSpan], str]:
    """
    Extracts armed flight spans from a ParsedLog object.
    Supports DataFlash (.bin) STAT/EV messages and MAVLink (.tlog) HEARTBEAT messages.
    """
    spans: List[FlightSpan] = []

    # 1. Try HEARTBEAT (MAVLink tlog)
    # Sort to prioritize sysid 1 (e.g. HEARTBEAT[S1] over HEARTBEAT[S255])
    hb_keys = [k for k in parsed.field_tree.keys() if k.startswith('HEARTBEAT')]
    hb_keys.sort(key=lambda k: 0 if '[S1]' in k else (1 if '[S' in k else 2))

    for hb_key in hb_keys:
        t_arr = parsed.timestamps.get(hb_key)
        base_mode = parsed.time_series.get(f"{hb_key}.base_mode")
        if t_arr is not None and base_mode is not None and len(t_arr) > 0:
            armed_arr = (base_mode.astype(int) & 128) != 0
            if np.any(armed_arr):
                diff = np.diff(armed_arr.astype(int))
                arm_indices = list(np.where(diff == 1)[0] + 1)
                disarm_indices = list(np.where(diff == -1)[0] + 1)

                if armed_arr[0]:
                    arm_indices.insert(0, 0)
                if armed_arr[-1]:
                    disarm_indices.append(len(armed_arr) - 1)

                for a_idx, d_idx in zip(arm_indices, disarm_indices):
                    t0 = float(t_arr[a_idx])
                    t1 = float(t_arr[d_idx])
                    dur = t1 - t0
                    if dur > 0.5:  # Ignore micro glitches (<0.5s)
                        spans.append(FlightSpan(start_time=t0, end_time=t1, duration=dur))

                if spans:
                    return True, spans, f"{hb_key}.base_mode"

    # 2. Try STAT (DataFlash bin)
    stat_keys = [k for k in parsed.field_tree.keys() if k.startswith('STAT')]
    for stat_key in stat_keys:
        t_arr = parsed.timestamps.get(stat_key)
        armed_val = parsed.time_series.get(f"{stat_key}.Armed")
        if armed_val is None:
            armed_val = parsed.time_series.get(f"{stat_key}.Arm")
        if armed_val is None:
            armed_val = parsed.time_series.get(f"{stat_key}.ArmState")

        if t_arr is not None and armed_val is not None and len(t_arr) > 0:
            armed_arr = armed_val.astype(int) > 0
            if np.any(armed_arr):
                diff = np.diff(armed_arr.astype(int))
                arm_indices = list(np.where(diff == 1)[0] + 1)
                disarm_indices = list(np.where(diff == -1)[0] + 1)

                if armed_arr[0]:
                    arm_indices.insert(0, 0)
                if armed_arr[-1]:
                    disarm_indices.append(len(armed_arr) - 1)

                for a_idx, d_idx in zip(arm_indices, disarm_indices):
                    t0 = float(t_arr[a_idx])
                    t1 = float(t_arr[d_idx])
                    dur = t1 - t0
                    if dur > 0.5:
                        spans.append(FlightSpan(start_time=t0, end_time=t1, duration=dur))

                if spans:
                    return True, spans, f"{stat_key}.Armed"

    # 3. Try EV (DataFlash events: 10=ARMED, 11=DISARMED)
    ev_keys = [k for k in parsed.field_tree.keys() if k.startswith('EV')]
    for ev_key in ev_keys:
        t_arr = parsed.timestamps.get(ev_key)
        ev_id = parsed.time_series.get(f"{ev_key}.Id")
        if ev_id is None:
            ev_id = parsed.time_series.get(f"{ev_key}.Event")

        if t_arr is not None and ev_id is not None and len(t_arr) > 0:
            arm_times = []
            disarm_times = []
            for t, id_val in zip(t_arr, ev_id):
                if int(id_val) == 10:
                    arm_times.append(float(t))
                elif int(id_val) == 11:
                    disarm_times.append(float(t))

            if arm_times:
                for t0 in arm_times:
                    # Find corresponding disarm time after t0
                    t1_candidates = [t for t in disarm_times if t > t0]
                    t1 = t1_candidates[0] if t1_candidates else (float(t_arr[-1]) if len(t_arr) > 0 else t0 + 1.0)
                    dur = t1 - t0
                    if dur > 0.5:
                        spans.append(FlightSpan(start_time=t0, end_time=t1, duration=dur))

                if spans:
                    return True, spans, f"{ev_key}.Id (10/11)"

    return False, [], "none"


def extract_wind_stats(parsed: ParsedLog, flight_spans: List[FlightSpan]) -> Tuple[bool, Optional[float], Optional[float], str]:
    """
    Extracts average and max wind speed (m/s) during flight spans from a ParsedLog.
    """
    t_wind = None
    wind_spd = None
    src_name = ""

    # Search candidates for wind speed
    # Candidate 1: WIND message (speed, WS, or VelN/VelE)
    for prefix in ['', '[S1]', '[S2]']:
        mkey = f"WIND{prefix}"
        if mkey in parsed.timestamps:
            if f"{mkey}.speed" in parsed.time_series:
                t_wind = parsed.timestamps[mkey]
                wind_spd = parsed.time_series[f"{mkey}.speed"]
                src_name = f"{mkey}.speed"
                break
            elif f"{mkey}.WS" in parsed.time_series:
                t_wind = parsed.timestamps[mkey]
                wind_spd = parsed.time_series[f"{mkey}.WS"]
                src_name = f"{mkey}.WS"
                break
            elif f"{mkey}.VelN" in parsed.time_series and f"{mkey}.VelE" in parsed.time_series:
                t_wind = parsed.timestamps[mkey]
                vn = parsed.time_series[f"{mkey}.VelN"]
                ve = parsed.time_series[f"{mkey}.VelE"]
                wind_spd = np.sqrt(vn**2 + ve**2)
                src_name = f"{mkey}.VelN/VelE"
                break

    # Candidate 2: EKF messages NKF2 / XKF2 / XKFS / EKF2 / EKF3 (VWN, VWE)
    if wind_spd is None:
        for ekf_prefix in ['NKF2', 'XKF2', 'XKFS', 'EKF2', 'EKF3']:
            matching_keys = [k for k in parsed.timestamps.keys() if k == ekf_prefix or k.startswith(f"{ekf_prefix}[")]
            for mkey in matching_keys:
                vwn_key = f"{mkey}.VWN"
                vwe_key = f"{mkey}.VWE"
                if vwn_key in parsed.time_series and vwe_key in parsed.time_series:
                    t_wind = parsed.timestamps[mkey]
                    vwn = parsed.time_series[vwn_key]
                    vwe = parsed.time_series[vwe_key]
                    wind_spd = np.sqrt(vwn**2 + vwe**2)
                    src_name = f"{mkey}.VWN/VWE"
                    break
            if wind_spd is not None:
                break

    # Candidate 3: WIND_COV (wind_x, wind_y)
    if wind_spd is None:
        for prefix in ['', '[S1]']:
            mkey = f"WIND_COV{prefix}"
            if mkey in parsed.timestamps:
                wx_key = f"{mkey}.wind_x"
                wy_key = f"{mkey}.wind_y"
                if wx_key in parsed.time_series and wy_key in parsed.time_series:
                    t_wind = parsed.timestamps[mkey]
                    wx = parsed.time_series[wx_key]
                    wy = parsed.time_series[wy_key]
                    wind_spd = np.sqrt(wx**2 + wy**2)
                    src_name = f"{mkey}.wind_x/wind_y"
                    break

    # Candidate 4: AHR2 (wind_spd / wind_vel)
    if wind_spd is None:
        for prefix in ['', '[S1]']:
            mkey = f"AHR2{prefix}"
            if mkey in parsed.timestamps:
                for spd_f in ['wind_spd', 'wind_vel', 'wind_speed']:
                    if f"{mkey}.{spd_f}" in parsed.time_series:
                        t_wind = parsed.timestamps[mkey]
                        wind_spd = parsed.time_series[f"{mkey}.{spd_f}"]
                        src_name = f"{mkey}.{spd_f}"
                        break

    if wind_spd is None or t_wind is None or len(wind_spd) == 0:
        return False, None, None, "None"

    # Filter data during flight spans if armed flight spans exist
    if flight_spans:
        mask = np.zeros(len(t_wind), dtype=bool)
        for span in flight_spans:
            mask |= (t_wind >= span.start_time) & (t_wind <= span.end_time)
        flight_wind = wind_spd[mask]
        if len(flight_wind) == 0:
            flight_wind = wind_spd
    else:
        flight_wind = wind_spd

    # Filter out invalid negative or NaN values
    flight_wind = flight_wind[~np.isnan(flight_wind)]
    flight_wind = flight_wind[flight_wind >= 0.0]

    if len(flight_wind) == 0:
        return False, None, None, src_name

    avg_w = float(np.mean(flight_wind))
    max_w = float(np.max(flight_wind))
    return True, avg_w, max_w, src_name


def analyze_log_summary(parsed: ParsedLog) -> LogSummary:
    """
    Computes a comprehensive summary for a ParsedLog.
    """
    summary = LogSummary(
        filename=parsed.filename,
        log_type=parsed.log_type
    )

    # 1. Total log duration
    all_times = []
    for t_arr in parsed.timestamps.values():
        if len(t_arr) > 0:
            all_times.append(float(t_arr[0]))
            all_times.append(float(t_arr[-1]))
    if all_times:
        summary.total_log_duration = max(all_times) - min(all_times)

    # 2. Extract flight spans
    has_arm, spans, arm_src = extract_flight_spans(parsed)
    summary.has_arming_data = has_arm
    summary.arming_source = arm_src
    summary.flight_spans = spans
    summary.flight_count = len(spans)

    if spans:
        # Pick the longest flight span as requested by requirement 1
        summary.longest_flight_span = max(spans, key=lambda s: s.duration)
        summary.total_armed_duration = sum(s.duration for s in spans)

    # 3. Extract wind speed stats
    has_wind, avg_w, max_w, wind_src = extract_wind_stats(parsed, spans if has_arm else [])
    summary.has_wind_data = has_wind
    summary.wind_source = wind_src
    summary.avg_wind_speed_ms = avg_w
    summary.max_wind_speed_ms = max_w

    return summary
