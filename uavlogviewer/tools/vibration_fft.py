"""
vibration_fft.py — High-performance FFT spectral analysis and ArduPilot vibration calculation.

Implements:
1. FFT Conversion with Hanning windowing and detrending.
2. Longest continuous segment extraction for gap-tolerant frequency estimation.
3. ArduPilot standard 5Hz Floor LPF + 2Hz Vibe LPF real-time vibration calculation (1D and 3D).

Dependencies: numpy.
"""
from typing import Tuple, Optional
import numpy as np


def compute_fft(y: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes single-sided FFT amplitude magnitude spectrum of a 1D signal.

    Args:
        y: 1D input array of signal values.
        fs: Sampling frequency in Hz.

    Returns:
        (freqs, mags): Tuple of frequency array (Hz) from 0 to fs/2 and amplitude magnitude array.
    """
    y_arr = np.asarray(y, dtype=np.float64)
    n = len(y_arr)
    if n < 2 or fs <= 0:
        return np.array([0.0]), np.array([0.0])

    # 1. Detrend signal by removing mean (DC offset)
    y_detrended = y_arr - np.mean(y_arr)

    # 2. Apply Hanning window
    window = np.hanning(n)
    y_windowed = y_detrended * window

    # 3. Real FFT
    fft_vals = np.fft.rfft(y_windowed)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)

    # 4. Normalized amplitude magnitude
    mags = np.abs(fft_vals) / n * 2.0
    return freqs, mags


def extract_fft_segment(
    timestamps: np.ndarray,
    values: np.ndarray,
    mode: str = "longest",
    gap_multiplier: float = 20.0,
    min_gap_s: float = 0.05
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Extracts continuous segment for FFT to prevent frequency bin distortion from data gaps.

    Args:
        timestamps: 1D array of timestamps (in seconds).
        values: 1D array of signal values.
        mode: "longest" or "all". Even in "all", large gaps are avoided by selecting the dominant continuous run.
        gap_multiplier: Multiplier on median dt to declare a gap.
        min_gap_s: Minimum gap duration in seconds to consider a boundary.

    Returns:
        (seg_timestamps, seg_values, fs): Segment arrays and estimated sample rate in Hz.
    """
    t_arr = np.asarray(timestamps, dtype=np.float64)
    y_arr = np.asarray(values, dtype=np.float64)

    if len(t_arr) < 2 or len(y_arr) < 2:
        return t_arr, y_arr, 0.0

    # Ensure equal length
    min_len = min(len(t_arr), len(y_arr))
    t_arr = t_arr[:min_len]
    y_arr = y_arr[:min_len]

    diffs = np.diff(t_arr)
    positive_diffs = diffs[diffs > 0]
    if len(positive_diffs) == 0:
        return t_arr, y_arr, 0.0

    median_dt = float(np.median(positive_diffs))
    if median_dt <= 0:
        return t_arr, y_arr, 0.0

    gap_threshold = max(median_dt * gap_multiplier, min_gap_s)
    gap_indices = np.flatnonzero(diffs > gap_threshold)

    starts = np.r_[0, gap_indices + 1]
    ends = np.r_[gap_indices, len(t_arr) - 1]

    sample_counts = ends - starts + 1
    best_idx = int(np.argmax(sample_counts))

    start_idx = int(starts[best_idx])
    end_idx = int(ends[best_idx])

    seg_t = t_arr[start_idx : end_idx + 1]
    seg_y = y_arr[start_idx : end_idx + 1]

    # Calculate sampling rate from segment
    seg_diffs = np.diff(seg_t)
    pos_seg_diffs = seg_diffs[seg_diffs > 0]
    if len(pos_seg_diffs) > 0:
        seg_median_dt = float(np.median(pos_seg_diffs))
        fs = 1.0 / seg_median_dt if seg_median_dt > 0 else 0.0
    else:
        duration = float(seg_t[-1] - seg_t[0])
        fs = (len(seg_t) - 1) / duration if duration > 0 else 0.0

    return seg_t, seg_y, fs


def compute_ap_vibration(
    values: np.ndarray,
    timestamps: np.ndarray,
    floor_cutoff_hz: float = 5.0,
    vibe_cutoff_hz: float = 2.0
) -> np.ndarray:
    """
    Computes vibration levels using ArduPilot's standard real-time method:
    1. Floor Filter: 5.0 Hz low pass on raw signal
    2. diff = val - floor_filt
    3. diff_sq = diff ** 2
    4. Vibe Filter: 2.0 Hz low pass on diff_sq
    5. vibe = sqrt(max(vibe_filt_sq, 0))

    Args:
        values: 1D array of signal values.
        timestamps: 1D array of timestamps (in seconds).
        floor_cutoff_hz: Floor filter cutoff in Hz (default: 5.0).
        vibe_cutoff_hz: Vibe filter cutoff in Hz (default: 2.0).

    Returns:
        1D array of vibration intensity matching the input length.
    """
    y = np.asarray(values, dtype=np.float64)
    t = np.asarray(timestamps, dtype=np.float64)
    n = min(len(y), len(t))

    out_vibe = np.zeros(len(y), dtype=np.float64)
    if n < 2:
        return out_vibe

    diffs = np.diff(t[:n])
    # Enforce positive dt with min bound 1 microsecond
    diffs = np.maximum(diffs, 1e-6)

    dt_arr = np.empty(n, dtype=np.float64)
    dt_arr[0] = diffs[0] if len(diffs) > 0 else 0.0025
    dt_arr[1:] = diffs

    rc_floor = 1.0 / (2.0 * np.pi * floor_cutoff_hz)
    rc_vibe = 1.0 / (2.0 * np.pi * vibe_cutoff_hz)

    alpha_floor = dt_arr / (dt_arr + rc_floor)
    np.clip(alpha_floor, 0.0, 1.0, out=alpha_floor)

    alpha_vibe = dt_arr / (dt_arr + rc_vibe)
    np.clip(alpha_vibe, 0.0, 1.0, out=alpha_vibe)

    floor_state = float(y[0])
    vibe_state = 0.0
    vibe_filt_sq = np.zeros(n, dtype=np.float64)

    for i in range(1, n):
        val = float(y[i])
        floor_state += alpha_floor[i] * (val - floor_state)
        accel_diff = val - floor_state
        accel_diff_sq = accel_diff * accel_diff

        if i == 1:
            vibe_state = accel_diff_sq
        else:
            vibe_state += alpha_vibe[i] * (accel_diff_sq - vibe_state)

        vibe_filt_sq[i] = vibe_state

    out_vibe[:n] = np.sqrt(np.maximum(vibe_filt_sq, 0.0))
    return out_vibe


def compute_ap_vibration_3d(
    arr_x: np.ndarray,
    arr_y: np.ndarray,
    arr_z: np.ndarray,
    timestamps: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes 3-axis vibration levels and composite magnitude using ArduPilot's method:
    mag = sqrt(vibe_x^2 + vibe_y^2 + vibe_z^2)

    Returns:
        (vibe_x, vibe_y, vibe_z, vibe_mag)
    """
    vx = compute_ap_vibration(arr_x, timestamps)
    vy = compute_ap_vibration(arr_y, timestamps)
    vz = compute_ap_vibration(arr_z, timestamps)
    vmag = np.sqrt(vx**2 + vy**2 + vz**2)
    return vx, vy, vz, vmag
