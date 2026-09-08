"""
log_reader — High-efficiency ArduPilot .bin log reader with segment detection.

Provides parallel binary parsing via mmap + struct, robust continuous-segment
detection, and data-rate estimation suitable for FFT and time-series analysis.

Dependencies: numpy, pandas, pymavlink (no others).

Typical usage::

    from src.log_reader import parse_bin_log, get_longest_segment, estimate_data_rate

    dfs = parse_bin_log("flight.bin", ["IMU", "XKF1", "BARO"])
    result = get_longest_segment(dfs["IMU"])
    print(f"IMU sample rate: {result.fs:.1f} Hz over {result.duration_s:.1f}s")
"""

from __future__ import annotations

import mmap
import os
import struct
from concurrent.futures import ProcessPoolExecutor
from typing import NamedTuple

import numpy as np
import pandas as pd
from pymavlink import mavutil

__all__ = [
    "parse_bin_log",
    "detect_segments",
    "get_longest_segment",
    "estimate_data_rate",
    "select_imu_instance",
    "compute_vector_magnitude",
    "SegmentInfo",
    "SegmentResult",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class SegmentInfo(NamedTuple):
    """Metadata for a single continuous time-series segment.

    Attributes:
        start_idx:   First row index (inclusive) in the source DataFrame.
        end_idx:     Last row index (inclusive) in the source DataFrame.
        start_us:    Timestamp (µs) of the first sample.
        end_us:      Timestamp (µs) of the last sample.
        duration_s:  Segment duration in seconds.
        samples:     Number of samples in the segment.
        median_dt_us: Median time-step within the segment (µs).
        fs:          Estimated sample rate (Hz) via ``(N-1) / duration``.
    """

    start_idx: int
    end_idx: int
    start_us: float
    end_us: float
    duration_s: float
    samples: int
    median_dt_us: float
    fs: float


class SegmentResult(NamedTuple):
    """The longest continuous segment together with its rate estimate.

    Attributes:
        df:             Sliced DataFrame of the longest segment.
        fs:             Estimated sample rate (Hz).
        start_us:       Timestamp (µs) of the first sample.
        end_us:         Timestamp (µs) of the last sample.
        duration_s:     Segment duration in seconds.
        samples:        Number of samples in the segment.
        median_dt_s:    Median time-step within the segment (seconds).
        total_segments: Total number of detected segments.
    """

    df: pd.DataFrame
    fs: float
    start_us: float
    end_us: float
    duration_s: float
    samples: int
    median_dt_s: float
    total_segments: int


# ---------------------------------------------------------------------------
# Parallel binary parser (internal worker — must be module-level for pickle)
# ---------------------------------------------------------------------------

def _parse_offsets_chunk(
    bin_path: str,
    offsets: list[int],
    msg_struct: str,
    msg_len: int,
    columns: list[str],
    msg_mults: list[float]
) -> tuple[pd.DataFrame, int]:
    """Unpack a chunk of message offsets and construct a scaled DataFrame."""
    import pandas as pd
    import numpy as np
    
    unpack_struct = struct.Struct(msg_struct)
    unpack_from = unpack_struct.unpack_from
    body_len = unpack_struct.size
    rows: list[tuple] = []
    skipped = 0

    with open(bin_path, "rb") as f:
        size = os.path.getsize(bin_path)
        if size == 0:
            return pd.DataFrame(columns=columns), 0
        data_map = mmap.mmap(f.fileno(), size, access=mmap.ACCESS_READ)
        try:
            for ofs in offsets:
                body_start = int(ofs) + 3
                if body_start + body_len > size:
                    skipped += 1
                    continue
                rows.append(unpack_from(data_map, body_start))
        finally:
            data_map.close()
            
    if not rows:
        return pd.DataFrame(columns=columns), skipped
        
    df = pd.DataFrame(rows, columns=columns)
    
    # Apply multipliers immediately in the worker process
    for i, col in enumerate(columns):
        if i < len(msg_mults):
            mul = msg_mults[i]
            if mul is not None and mul != 1.0:
                try:
                    if 0.0 < mul < 1.0:
                        df[col] = df[col] / (1.0 / mul)
                    else:
                        df[col] = df[col] * mul
                except Exception:
                    pass
                    
    return df, skipped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_bin_log(
    bin_path: str,
    target_types: list[str],
    *,
    ignore_gps_clock: str | bool = "auto",
    mlog: Any = None,
) -> dict[str, pd.DataFrame]:
    """High-performance parallel binary parser for ArduPilot ``.bin`` logs.

    Uses pymavlink for format discovery (message IDs, struct layouts, column
    names, and scaling multipliers), then dispatches mmap + struct unpacking
    across multiple worker processes for throughput.

    Args:
        bin_path:         Path to the ArduPilot ``.bin`` log file.
        target_types:     Message type names to extract (e.g. ``["IMU", "XKF1"]``).
        ignore_gps_clock: Bypasses pymavlink's sequential log scanning for GPS clock
                          synchronization. Options:
                          - ``"auto"`` (default): Automatically detects if there are any
                            GPS or clock-setting messages. If not, clock scanning is
                            bypassed for instant speedup.
                          - ``True``: Clock scanning is unconditionally bypassed.
                          - ``False``: Clock scanning is always executed.
        mlog:             Optional pre-scanned pymavlink connection object. If provided,
                          Phase 1 scanning is bypassed and mlog is kept open.

    Returns:
        A dict mapping each requested message type name to a
        :class:`pandas.DataFrame`.  Types not present in the log are
        returned as empty DataFrames with the correct column names when
        format information is available.

    Raises:
        FileNotFoundError: If *bin_path* does not exist.
        RuntimeError:      If pymavlink cannot open the log.

    Example::

        dfs = parse_bin_log("flight.bin", ["IMU", "BARO", "GPS"])
        print(dfs["IMU"].columns.tolist())
    """
    if not os.path.isfile(bin_path):
        raise FileNotFoundError(f"Log file not found: {bin_path}")

    # Deduplicate while preserving order
    target_types = list(dict.fromkeys(target_types))

    close_mlog = False
    if mlog is None:
        close_mlog = True
        # ------------------------------------------------------------------
        # Phase 1 — pymavlink scan (builds name_to_id, formats, offsets)
        # ------------------------------------------------------------------
        from pymavlink.DFReader import DFReader_binary, DFReaderClock_usec
        orig_init_clock = DFReader_binary.init_clock

        def fast_init_clock(self):
            self.clock = DFReaderClock_usec()
            self._rewind(keep_messages=True)

        def auto_init_clock(self):
            if hasattr(self, "offsets") and self.offsets is not None:
                gps_type = self.name_to_id.get("GPS")
                gps2_type = self.name_to_id.get("GPS2")
                time_type = self.name_to_id.get("TIME")

                has_gps = gps_type is not None and len(self.offsets[gps_type]) > 0
                has_gps2 = gps2_type is not None and len(self.offsets[gps2_type]) > 0
                has_time = time_type is not None and len(self.offsets[time_type]) > 0

                if not (has_gps or has_gps2 or has_time):
                    self.clock = DFReaderClock_usec()
                    self._rewind(keep_messages=True)
                    return
            return orig_init_clock(self)

        # Patch dynamically depending on mode
        if ignore_gps_clock is True:
            DFReader_binary.init_clock = fast_init_clock
        elif ignore_gps_clock == "auto":
            DFReader_binary.init_clock = auto_init_clock

        try:
            mlog = mavutil.mavlink_connection(bin_path)
        finally:
            DFReader_binary.init_clock = orig_init_clock

    # Count total offsets across target types
    total_offsets = 0
    for tname in target_types:
        tid = mlog.name_to_id.get(tname)
        if tid is not None and tid < len(mlog.offsets):
            total_offsets += len(mlog.offsets[tid])

    data_by_type: dict[str, list[pd.DataFrame]] = {t: [] for t in target_types}

    # If small workload, run sequentially in-process to avoid process pool overhead
    if total_offsets < 30_000:
        for tname in target_types:
            tid = mlog.name_to_id.get(tname)
            if tid is None or tid >= len(mlog.offsets):
                continue
            fmt = mlog.formats.get(tid)
            offsets = mlog.offsets[tid]
            if not fmt or len(offsets) == 0:
                continue
            df_chunk, _ = _parse_offsets_chunk(
                bin_path,
                offsets,
                fmt.msg_struct,
                fmt.len,
                fmt.columns,
                fmt.msg_mults
            )
            data_by_type[tname].append(df_chunk)
    else:
        # Determine worker count
        cpu_count = os.cpu_count() or 4
        if len(target_types) == 1:
            num_workers = min(4, cpu_count)
        else:
            num_workers = min(8, max(1, int(max(cpu_count - 4, cpu_count / 2))))

        # ------------------------------------------------------------------
        # Phase 2 & 3 — dispatch parallel unpacking and DataFrame construction
        # ------------------------------------------------------------------
        futures: list[tuple[str, object]] = []

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            for tname in target_types:
                tid = mlog.name_to_id.get(tname)
                if tid is None or tid >= len(mlog.offsets):
                    continue
                fmt = mlog.formats.get(tid)
                offsets = mlog.offsets[tid]
                if not fmt or len(offsets) == 0:
                    continue

                chunk_size = max(20_000, len(offsets) // num_workers)
                for i in range(0, len(offsets), chunk_size):
                    chunk = offsets[i : i + chunk_size]
                    futures.append((
                        tname,
                        executor.submit(
                            _parse_offsets_chunk,
                            bin_path,
                            chunk,
                            fmt.msg_struct,
                            fmt.len,
                            fmt.columns,
                            fmt.msg_mults
                        ),
                    ))

            for tname, future in futures:
                df_chunk, _ = future.result()
                data_by_type[tname].append(df_chunk)

    # Concatenate chunked DataFrames
    result: dict[str, pd.DataFrame] = {}

    for tname in target_types:
        df_list = data_by_type[tname]
        if not df_list:
            tid = mlog.name_to_id.get(tname)
            cols = mlog.formats[tid].columns if (tid is not None and tid in mlog.formats) else []
            result[tname] = pd.DataFrame(columns=cols)
            continue
            
        if len(df_list) == 1:
            result[tname] = df_list[0]
        else:
            result[tname] = pd.concat(df_list, ignore_index=True)

    # Close the pymavlink file handle if we created it
    if close_mlog and hasattr(mlog, 'close'):
        try:
            mlog.close()
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Segment detection
# ---------------------------------------------------------------------------

def detect_segments(
    df: pd.DataFrame,
    time_col: str = "TimeUS",
    gap_multiplier: float = 20.0,
    min_gap_s: float = 0.05,
) -> list[SegmentInfo]:
    """Detect continuous time-series segments separated by gaps.

    A gap is declared when a time difference exceeds
    ``max(median_dt * gap_multiplier, min_gap_s * 1e6)`` microseconds.

    Args:
        df:             DataFrame containing a monotonic time column.
        time_col:       Name of the time column (expected in microseconds).
        gap_multiplier: Factor applied to median dt to set the gap threshold.
        min_gap_s:      Absolute minimum gap threshold in seconds.

    Returns:
        A list of :class:`SegmentInfo` named tuples, one per continuous
        segment, ordered by their position in the DataFrame.

    Example::

        segments = detect_segments(df_imu)
        for seg in segments:
            print(f"{seg.samples} samples @ {seg.fs:.1f} Hz")
    """
    if df is None or df.empty or time_col not in df.columns:
        return []

    df_sorted = df.sort_values(time_col, kind="mergesort").reset_index(drop=True)
    time_us = df_sorted[time_col].to_numpy(dtype=np.float64)

    if len(time_us) < 2:
        # Single-sample segment
        t = float(time_us[0]) if len(time_us) == 1 else 0.0
        return [SegmentInfo(
            start_idx=0, end_idx=0,
            start_us=t, end_us=t,
            duration_s=0.0, samples=len(time_us),
            median_dt_us=0.0, fs=0.0,
        )]

    diffs_us = np.diff(time_us)
    positive = diffs_us[diffs_us > 0]

    if len(positive) == 0:
        return [SegmentInfo(
            start_idx=0, end_idx=len(df_sorted) - 1,
            start_us=float(time_us[0]), end_us=float(time_us[-1]),
            duration_s=0.0, samples=len(df_sorted),
            median_dt_us=0.0, fs=0.0,
        )]

    median_dt = float(np.median(positive))
    gap_threshold_us = max(median_dt * gap_multiplier, min_gap_s * 1e6)

    gap_indices = np.flatnonzero(diffs_us > gap_threshold_us)
    starts = np.r_[0, gap_indices + 1]
    ends = np.r_[gap_indices, len(df_sorted) - 1]

    segments: list[SegmentInfo] = []
    for s, e in zip(starts, ends):
        s_int, e_int = int(s), int(e)
        seg_time = time_us[s_int : e_int + 1]
        n = len(seg_time)
        t0, t1 = float(seg_time[0]), float(seg_time[-1])
        dur_s = (t1 - t0) * 1e-6

        # Median dt within segment
        if n >= 2:
            seg_diffs = np.diff(seg_time)
            seg_pos = seg_diffs[seg_diffs > 0]
            seg_median_dt = float(np.median(seg_pos)) if len(seg_pos) else median_dt
        else:
            seg_median_dt = median_dt

        # Primary fs estimator: (N-1) / duration
        if dur_s > 0:
            fs = (n - 1) / dur_s
        elif seg_median_dt > 0:
            fs = 1e6 / seg_median_dt
        else:
            fs = 0.0

        segments.append(SegmentInfo(
            start_idx=s_int,
            end_idx=e_int,
            start_us=t0,
            end_us=t1,
            duration_s=dur_s,
            samples=n,
            median_dt_us=seg_median_dt,
            fs=fs,
        ))

    return segments


def get_longest_segment(
    df: pd.DataFrame,
    time_col: str = "TimeUS",
    gap_multiplier: float = 20.0,
    min_gap_s: float = 0.05,
) -> SegmentResult:
    """Return the longest continuous segment and its rate metadata.

    Selection logic:

    1. Prefer segments with **>100 samples** (avoids noisy micro-segments).
    2. Among qualifying segments pick the one with the longest duration.
    3. If no segment exceeds 100 samples, pick by largest sample count.

    The sample rate ``fs`` is estimated as ``(N-1) / duration_s`` — this
    avoids the bimodal-dt problem (e.g. ILB's alternating 3.33 ms / 6.66 ms
    spacing) that causes median-based estimates to be wrong.

    Args:
        df:             DataFrame containing a monotonic time column.
        time_col:       Name of the time column (expected in microseconds).
        gap_multiplier: Factor applied to median dt for gap threshold.
        min_gap_s:      Absolute minimum gap threshold in seconds.

    Returns:
        A :class:`SegmentResult` named tuple.  If the input is empty or
        unusable, all numeric fields are zero and ``df`` is empty.

    Example::

        result = get_longest_segment(dfs["IMU"])
        print(f"{result.fs:.1f} Hz, {result.samples} pts, "
              f"{result.total_segments} segments detected")
    """
    _empty = SegmentResult(
        df=pd.DataFrame(), fs=0.0, start_us=0.0, end_us=0.0,
        duration_s=0.0, samples=0, median_dt_s=0.0, total_segments=0,
    )

    segments = detect_segments(df, time_col, gap_multiplier, min_gap_s)
    if not segments:
        return _empty

    # Sort and select best segment
    sample_counts = np.array([s.samples for s in segments])
    durations = np.array([s.duration_s for s in segments])

    valid_mask = sample_counts > 100
    if np.any(valid_mask):
        valid_idx = np.flatnonzero(valid_mask)
        best_idx = int(valid_idx[np.argmax(durations[valid_idx])])
    else:
        best_idx = int(np.argmax(sample_counts))

    best = segments[best_idx]

    # Re-sort the dataframe to match segment detection order
    df_sorted = df.sort_values(time_col, kind="mergesort").reset_index(drop=True)
    seg_df = df_sorted.iloc[best.start_idx : best.end_idx + 1].copy()

    # Primary fs estimator: (N-1) / duration_s
    if best.duration_s > 0:
        fs = (best.samples - 1) / best.duration_s
    elif best.median_dt_us > 0:
        fs = 1e6 / best.median_dt_us
    else:
        fs = 0.0

    return SegmentResult(
        df=seg_df,
        fs=fs,
        start_us=best.start_us,
        end_us=best.end_us,
        duration_s=best.duration_s,
        samples=best.samples,
        median_dt_s=best.median_dt_us * 1e-6,
        total_segments=len(segments),
    )


def estimate_data_rate(
    df: pd.DataFrame,
    time_col: str = "TimeUS",
    gap_multiplier: float = 20.0,
    min_gap_s: float = 0.05,
) -> float:
    """Estimate the effective sampling rate (Hz), robust to time gaps.

    Internally calls :func:`detect_segments`, selects the longest segment,
    and computes ``(N-1) / duration_s`` within it.

    Args:
        df:             DataFrame with a monotonic time column.
        time_col:       Name of the time column (microseconds).
        gap_multiplier: Gap-detection multiplier on median dt.
        min_gap_s:      Minimum gap threshold in seconds.

    Returns:
        Estimated sample rate in Hz, or ``0.0`` if estimation fails.
    """
    result = get_longest_segment(df, time_col, gap_multiplier, min_gap_s)
    return result.fs


# ---------------------------------------------------------------------------
# IMU helpers
# ---------------------------------------------------------------------------

def select_imu_instance(
    df_imu: pd.DataFrame,
    instance: int = 0,
) -> pd.DataFrame:
    """Filter an IMU DataFrame to a single hardware instance.

    ArduPilot logs multiple IMU instances (0, 1, 2...) in a single message
    type using an ``I`` or ``instance`` column.

    Args:
        df_imu:   DataFrame containing IMU data with an instance column.
        instance: Hardware instance number to select (default 0).

    Returns:
        A filtered copy of *df_imu* containing only rows matching
        *instance*.  Returns an empty DataFrame (preserving columns) if
        the instance column is missing or no rows match.
    """
    # Try common column names for the instance field
    inst_col: str | None = None
    for candidate in ("I", "instance", "Instance", "IMU"):
        if candidate in df_imu.columns:
            inst_col = candidate
            break

    if inst_col is None:
        return df_imu.copy()

    mask = df_imu[inst_col] == instance
    return df_imu.loc[mask].reset_index(drop=True)


def compute_vector_magnitude(
    df: pd.DataFrame,
    cols: list[str],
    out_col: str = "magnitude",
) -> pd.DataFrame:
    """Add a column with the Euclidean magnitude of the given component columns.

    Args:
        df:      Source DataFrame.
        cols:    Column names whose squared values are summed (e.g.
                 ``["AccX", "AccY", "AccZ"]``).
        out_col: Name of the new magnitude column.

    Returns:
        A copy of *df* with *out_col* appended.

    Raises:
        KeyError: If any column in *cols* is missing from *df*.
    """
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"Missing columns: {missing}")

    df = df.copy()
    sq_sum = np.zeros(len(df), dtype=np.float64)
    for c in cols:
        sq_sum += df[c].to_numpy(dtype=np.float64) ** 2
    df[out_col] = np.sqrt(sq_sum)
    return df
