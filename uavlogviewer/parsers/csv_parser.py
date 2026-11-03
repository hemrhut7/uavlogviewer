"""
csv_parser.py — High-performance, universal parser for UAV and sensor CSV logs.

Supports:
- InertialLabs IMU / INS logs (e.g. with '# Start Time:' comments and 'wx,wy,wz,ax,ay,az,time')
- DJI telemetry CSV exports
- ArduPilot / PX4 CSV logs
- Generic tabular telemetry CSV files with arbitrary sensors and timestamps
- Parameter CSV files (e.g. Parameter,Value)

Dependencies: pandas, numpy, base_parser.
"""
import os
import re
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from uavlogviewer.parsers.base_parser import (
    BaseParser,
    ParsedLog,
    calculate_data_rate,
    LogEvent
)


TIME_COLUMN_CANDIDATES = [
    'time', 'timestamp', 'time_s', 'time(s)', 'time [s]', 'time_sec',
    'offsettime', 'time(millisecond)', 'timems', 'time_ms', 'time_us',
    'time_usec', 't', 'tick', 'ticks', 'tow', 'gpstime', 'utc'
]


def detect_separator(filepath: str) -> str:
    """Detects delimiter (comma, semicolon, tab) by counting candidate frequencies on the header line."""
    sep = ','
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_str = line.strip()
                if not line_str or line_str.startswith(('#', '//')):
                    continue
                candidates = [',', ';', '\t']
                counts = {c: line_str.count(c) for c in candidates}
                best_sep = max(counts, key=counts.get)
                if counts[best_sep] > 0:
                    sep = best_sep
                break
    except Exception:
        sep = ','
    return sep


def extract_header_comments(filepath: str) -> Tuple[Dict[str, str], List[str]]:
    """Extracts metadata from leading comment lines (e.g., '# Start Time: ...')."""
    metadata: Dict[str, str] = {}
    comment_lines: List[str] = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.startswith(('#', '//')):
                    clean_comment = line_str.lstrip('#/').strip()
                    comment_lines.append(clean_comment)
                    if ':' in clean_comment:
                        k, v = clean_comment.split(':', 1)
                        clean_k = re.sub(r'\s+', '_', k.strip())
                        metadata[clean_k] = v.strip()
                else:
                    # Reached data/header
                    break
    except Exception:
        pass
    return metadata, comment_lines


def determine_default_group_name(filename: str, cols: List[str]) -> str:
    """Determines an intuitive message group name based on filename and column names."""
    fn_lower = filename.lower()
    cols_lower = [c.lower() for c in cols]

    # Check for IMU characteristics
    has_imu_cols = any(c in ('wx', 'wy', 'wz') for c in cols_lower) and any(c in ('ax', 'ay', 'az') for c in cols_lower)
    if 'imu' in fn_lower or has_imu_cols:
        return 'IMU'

    # Check for INS characteristics
    if 'ins' in fn_lower:
        return 'INS'

    # Check for GPS characteristics
    has_gps_cols = any('lat' in c for c in cols_lower) and any('lon' in c or 'lng' in c for c in cols_lower)
    if 'gps' in fn_lower or has_gps_cols:
        return 'GPS'

    # Check for Attitude characteristics
    has_att_cols = any('roll' in c for c in cols_lower) and any('pitch' in c for c in cols_lower)
    if 'att' in fn_lower or has_att_cols:
        return 'ATT'

    # Check for Barometer characteristics
    if 'baro' in fn_lower or any('press' in c for c in cols_lower):
        return 'BARO'

    # Check for Magnetometer characteristics
    if 'mag' in fn_lower:
        return 'MAG'

    # Check for DJI
    if any(c in cols for c in ['offsetTime', 'time(millisecond)', 'Tick']):
        return 'DJI'

    # Fallback to sanitized filename stem (without timestamp suffixes)
    base_name = os.path.splitext(filename)[0]
    # Remove common timestamp patterns like _20260917_143651 or -2026-09-17
    cleaned_stem = re.sub(r'[_\-]?\d{8}[_\-]\d{4,6}.*$', '', base_name)
    cleaned_stem = re.sub(r'[_\-]\d{4}[_\-]\d{2}[_\-]\d{2}.*$', '', cleaned_stem)
    cleaned_stem = re.sub(r'[^a-zA-Z0-9_]', '_', cleaned_stem).strip('_')

    if cleaned_stem and not cleaned_stem.isdigit() and len(cleaned_stem) <= 20:
        return cleaned_stem.upper()

    return 'CSV'


class CsvParser(BaseParser):
    """Robust, high-throughput CSV log parser."""

    def parse(self, filepath: str) -> ParsedLog:
        filename = os.path.basename(filepath)
        parsed = ParsedLog(
            filename=filename,
            log_type="csv"
        )

        metadata, comment_lines = extract_header_comments(filepath)
        if metadata:
            parsed.params.update(metadata)
        for c in comment_lines:
            parsed.text_messages.append({"time": 0.0, "msg": c})

        sep = detect_separator(filepath)

        try:
            # Using C engine when sep is single character and skipping scanned comment lines
            df = pd.read_csv(filepath, sep=sep, skiprows=len(comment_lines), comment='#', low_memory=False)
        except Exception as e:
            # Fallback to python engine
            try:
                df = pd.read_csv(filepath, sep=None, skiprows=len(comment_lines), comment='#', engine='python')
            except Exception as e2:
                import logging
                logging.getLogger(__name__).warning("Failed to parse CSV %s: %s / %s", filepath, e, e2)
                return parsed

        if df.empty:
            return parsed

        # Strip whitespace from column names
        df.columns = [str(c).strip() for c in df.columns]

        # Check if this is a Parameter file (e.g. Parameter,Value or Name,Value)
        col_set_lower = [c.lower() for c in df.columns]
        if len(df.columns) == 2 and ('parameter' in col_set_lower or 'param' in col_set_lower or 'name' in col_set_lower):
            if any(k in df.columns[0].lower() for k in ('param', 'name')):
                param_col, val_col = df.columns[0], df.columns[1]
            else:
                param_col, val_col = df.columns[1], df.columns[0]
            parsed.params.update(dict(zip(df[param_col].astype(str).str.strip(), df[val_col])))
            parsed.log_type = "csv_param"
            return parsed

        # Locate time column (supports normal and dotted columns like 'IMU.time')
        time_col = None
        for candidate in TIME_COLUMN_CANDIDATES:
            for col in df.columns:
                leaf_col = col.split('.')[-1].lower()
                if leaf_col == candidate:
                    time_col = col
                    break
            if time_col:
                break

        # Fallback time search by regex prefix if not found
        if not time_col:
            for col in df.columns:
                leaf_col = col.split('.')[-1].lower()
                if leaf_col.startswith(('time', 'timestamp', 'offsettime', 'tick')):
                    time_col = col
                    break

        n_rows = len(df)
        if time_col is not None:
            time_series = df[time_col]
            # If time column is ISO datetime or string/object, parse to elapsed seconds
            if not pd.api.types.is_numeric_dtype(time_series.dtype):
                try:
                    num_series = pd.to_numeric(time_series, errors='coerce')
                    if num_series.notna().sum() > 0.5 * n_rows:
                        time_arr = num_series.fillna(0.0).to_numpy(dtype=np.float64)
                    else:
                        dt_series = pd.to_datetime(time_series, errors='coerce')
                        valid_dt = dt_series.dropna()
                        t0 = valid_dt.iloc[0] if not valid_dt.empty else dt_series.iloc[0]
                        time_arr = (dt_series - t0).dt.total_seconds().fillna(0.0).to_numpy(dtype=np.float64)
                except Exception:
                    time_arr = pd.to_numeric(time_series, errors='coerce').fillna(0.0).to_numpy(dtype=np.float64)
            else:
                time_arr = time_series.to_numpy(dtype=np.float64)

            # Check unit scaling
            time_max = float(np.nanmax(time_arr)) if len(time_arr) > 0 else 0.0
            col_lower = time_col.lower()
            is_micro = any(k in col_lower for k in ('microsecond', 'time_us', 'timeus', 'usec'))
            is_milli = any(k in col_lower for k in ('millisecond', 'time_ms', 'timems', 'offsettime'))
            if is_micro or (time_max > 1e8 and not is_milli):
                time_arr = time_arr / 1e6
            elif is_milli or (time_max > 1e5 and not any(k in col_lower for k in ('gpstime', 'tow', 'unix', 'epoch'))):
                time_arr = time_arr / 1000.0
        else:
            # No time column found: synthesize default timestamp array (dt = 0.1s)
            time_arr = np.arange(n_rows, dtype=np.float64) * 0.1

        # Check if columns are dotted (e.g. 'IMU.ax', 'GPS.lat')
        has_dotted = any('.' in col for col in df.columns if col != time_col)

        default_group = determine_default_group_name(filename, list(df.columns))

        groups: Dict[str, List[str]] = {}

        for col in df.columns:
            if col == time_col:
                continue

            if has_dotted and '.' in col:
                grp, field = col.split('.', 1)
            else:
                grp = default_group
                field = col

            if grp not in groups:
                groups[grp] = []
            groups[grp].append((field, col))

        # Register timestamps and series per group
        for grp, field_list in groups.items():
            parsed.timestamps[grp] = time_arr
            parsed.field_tree[grp] = []

            # Estimate data rate
            rate = calculate_data_rate(time_arr)
            if rate > 0:
                parsed.estimated_rates[grp] = rate

            for field_name, original_col in field_list:
                col_data = df[original_col]
                if np.issubdtype(col_data.dtype, np.floating) and not col_data.hasnans:
                    series = col_data.to_numpy(dtype=np.float64, copy=False)
                else:
                    series = pd.to_numeric(col_data, errors='coerce').fillna(0.0).to_numpy(dtype=np.float64)
                full_key = f"{grp}.{field_name}"
                parsed.time_series[full_key] = series
                parsed.field_tree[grp].append(field_name)

        if len(time_arr) > 1:
            parsed.total_log_duration = float(time_arr[-1] - time_arr[0])

        return parsed
