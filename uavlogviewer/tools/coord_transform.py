"""
coord_transform.py — WGS-84 LLH to ENU Coordinate Transformation Engine.

Converts geodetic coordinates (Latitude, Longitude, Altitude) to local ENU
(East, North, Up) tangent plane coordinates relative to the 1st valid data point as reference origin.

Reference implementation:
/home/hank/Github/ABC_ROS/src/INS_python/nav_ekf/core/coordinate_transformation.py

Dependencies: numpy, base_parser.
"""

import numpy as np
from typing import Tuple, Dict, List, Optional, Any
from uavlogviewer.parsers.base_parser import ParsedLog

# WGS84 Reference Ellipsoid Parameters
WGS84_A = 6378137.0         # Semi-major axis (meters)
WGS84_E = 0.08181919        # Eccentricity
WGS84_E_SQ = WGS84_E ** 2   # Square of eccentricity

def earth_radii(lat_rad: float) -> Tuple[float, float]:
    """
    Calculates meridian radius of curvature (rm) and prime vertical radius of curvature (rn)
    for a given latitude in radians.
    """
    sin_lat = np.sin(lat_rad)
    w2 = 1.0 - WGS84_E_SQ * (sin_lat ** 2)
    rn = WGS84_A / np.sqrt(w2)
    rm = rn * (1.0 - WGS84_E_SQ) / w2
    return rm, rn

def llh2enu(
    target_pos: np.ndarray,
    ref_pos: np.ndarray,
    is_3d: bool = True
) -> np.ndarray:
    """
    Transforms WGS84 Geodetic coordinates (lat_rad, lon_rad, alt_m) into East-North-Up (ENU)
    local tangent plane coordinates (meters) relative to ref_pos.

    Parameters:
        target_pos: (3,) or (N, 3) array of [lat_rad, lon_rad, alt_m]
        ref_pos: (3,) array of [ref_lat_rad, ref_lon_rad, ref_alt_m]
        is_3d: if True returns 3D [E, N, U], else 2D [E, N]

    Returns:
        np.ndarray of ENU coordinates in meters
    """
    target_pos = np.asarray(target_pos, dtype=np.float64)
    ref_pos = np.asarray(ref_pos, dtype=np.float64)
    rm, rn = earth_radii(ref_pos[0])

    if target_pos.ndim == 1:
        e = (target_pos[1] - ref_pos[1]) * (rn + ref_pos[2]) * np.cos(ref_pos[0])
        n = (target_pos[0] - ref_pos[0]) * (rm + ref_pos[2])
        if is_3d:
            return np.array([e, n, target_pos[2] - ref_pos[2]])
        return np.array([e, n])
    else:
        e = (target_pos[:, 1] - ref_pos[1]) * (rn + ref_pos[2]) * np.cos(ref_pos[0])
        n = (target_pos[:, 0] - ref_pos[0]) * (rm + ref_pos[2])
        if is_3d:
            u = target_pos[:, 2] - ref_pos[2]
            return np.column_stack((e, n, u))
        return np.column_stack((e, n))

def convert_llh_series_to_enu(
    lat_arr: np.ndarray,
    lon_arr: np.ndarray,
    alt_arr: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Tuple[float, float, float]]:
    """
    Converts 1D series of Lat, Lon, Alt into ENU series taking the 1st valid data point as reference origin.

    Returns:
        e_arr (meters), n_arr (meters), u_arr (meters), origin_tuple (ref_lat_deg, ref_lon_deg, ref_alt_m)
    """
    lat_arr = np.asarray(lat_arr, dtype=np.float64)
    lon_arr = np.asarray(lon_arr, dtype=np.float64)
    alt_arr = np.asarray(alt_arr, dtype=np.float64)

    # Automatically handle 1e7 integer scaling (e.g. ArduPilot DataFlash GPS.Lat = 239738750)
    if np.nanmax(np.abs(lat_arr)) > 180.0:
        lat_deg = lat_arr / 1e7
    else:
        lat_deg = lat_arr.copy()

    if np.nanmax(np.abs(lon_arr)) > 180.0:
        lon_deg = lon_arr / 1e7
    else:
        lon_deg = lon_arr.copy()

    # Find 1st valid index for origin (exclude 0,0 un-fixed GPS points before satellite lock)
    valid_fix_mask = (
        ~np.isnan(lat_deg) & ~np.isnan(lon_deg) & ~np.isnan(alt_arr) &
        (np.abs(lat_deg) > 0.001) & (np.abs(lon_deg) > 0.001)
    )
    valid_indices = np.flatnonzero(valid_fix_mask)

    if len(valid_indices) == 0:
        # Fall back to any non-NaN points if all points are 0 or invalid
        fallback_mask = ~np.isnan(lat_deg) & ~np.isnan(lon_deg) & ~np.isnan(alt_arr)
        valid_indices = np.flatnonzero(fallback_mask)

    if len(valid_indices) == 0:
        ref_lat_deg, ref_lon_deg, ref_alt_m = 0.0, 0.0, 0.0
    else:
        i0 = valid_indices[0]
        ref_lat_deg = float(lat_deg[i0])
        ref_lon_deg = float(lon_deg[i0])
        ref_alt_m = float(alt_arr[i0])

    ref_lat_rad = np.radians(ref_lat_deg)
    ref_lon_rad = np.radians(ref_lon_deg)
    ref_pos = np.array([ref_lat_rad, ref_lon_rad, ref_alt_m])

    lat_rad = np.radians(lat_deg)
    lon_rad = np.radians(lon_deg)
    target_pos = np.column_stack((lat_rad, lon_rad, alt_arr))

    enu = llh2enu(target_pos, ref_pos, is_3d=True)

    e, n, u = enu[:, 0], enu[:, 1], enu[:, 2]

    # Mark un-fixed 0,0 or NaN points as NaN so Plotly doesn't distort graph scale to equator
    invalid_mask = (
        np.isnan(lat_deg) | np.isnan(lon_deg) | np.isnan(alt_arr) |
        ((np.abs(lat_deg) < 0.001) & (np.abs(lon_deg) < 0.001))
    )
    e[invalid_mask] = np.nan
    n[invalid_mask] = np.nan
    u[invalid_mask] = np.nan

    return e, n, u, (ref_lat_deg, ref_lon_deg, ref_alt_m)

def _find_best_field(fields: List[str], target_keywords: List[str], exclude_keywords: List[str] = None) -> Optional[str]:
    """Helper to match field names prioritizing exact match first, then partial match."""
    exclude_keywords = exclude_keywords or []
    
    # Filter out excluded fields (e.g. status, error)
    cand_fields = [f for f in fields if not any(ex in f.lower() for ex in exclude_keywords)]

    # 1. Exact match (case-insensitive)
    for kw in target_keywords:
        for f in cand_fields:
            if f.lower() == kw:
                return f

    # 2. Starts with / prefix match
    for kw in target_keywords:
        for f in cand_fields:
            if f.lower().startswith(kw):
                return f

    # 3. Contains match
    for kw in target_keywords:
        for f in cand_fields:
            if kw in f.lower():
                return f

    return None

def detect_llh_messages(parsed_log: ParsedLog) -> List[Dict[str, Any]]:
    """
    Scans parsed_log.field_tree for message types containing Lat, Lon, Alt fields simultaneously.

    Returns a list of candidate dictionaries:
    [
        {
            'msg_type': 'GPS',
            'lat_field': 'Lat',
            'lon_field': 'Lng',
            'alt_field': 'Alt',
            'lat_key': 'GPS.Lat',
            'lon_key': 'GPS.Lng',
            'alt_key': 'GPS.Alt',
            'samples': 1250
        },
        ...
    ]
    """
    if not parsed_log or not parsed_log.field_tree:
        return []

    candidates: List[Dict[str, Any]] = []

    for msg_type, fields in parsed_log.field_tree.items():
        if msg_type == "CALC" or not fields:
            continue

        lat_field = _find_best_field(fields, ['lat', 'latitude'], exclude_keywords=['status', 'err', 'acc'])
        lon_field = _find_best_field(fields, ['lon', 'lng', 'longitude'], exclude_keywords=['status', 'err', 'acc'])
        alt_field = _find_best_field(fields, ['alt', 'altitude', 'h', 'height'], exclude_keywords=['status', 'err', 'target', 'sp'])

        if lat_field and lon_field and alt_field:
            lat_key = f"{msg_type}.{lat_field}"
            lon_key = f"{msg_type}.{lon_field}"
            alt_key = f"{msg_type}.{alt_field}"

            if (lat_key in parsed_log.time_series and
                lon_key in parsed_log.time_series and
                alt_key in parsed_log.time_series):
                
                n_samples = len(parsed_log.time_series[lat_key])
                if n_samples > 0:
                    candidates.append({
                        'msg_type': msg_type,
                        'lat_field': lat_field,
                        'lon_field': lon_field,
                        'alt_field': alt_field,
                        'lat_key': lat_key,
                        'lon_key': lon_key,
                        'alt_key': alt_key,
                        'samples': n_samples
                    })

    return candidates
