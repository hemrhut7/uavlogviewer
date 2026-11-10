"""
csv_exporter.py — High-performance exporter for saving plotted messages and telemetry fields to CSV.

Supports:
- Exporting plotted fields only or all fields of plotted message types.
- Multi-rate timestamp alignment via sorted timestamp union (exact/raw) or forward-fill (zero-order hold).
- Time range filtering (full log, current visible range [x0, x1], or segment filter).
- Standard timeseries expressions, XY scatter pairs, and CALC expressions.

Dependencies: pandas, numpy, uavlogviewer.models.chart_store, uavlogviewer.parsers.base_parser.
"""
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
import pandas as pd
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.models.log_session import LogSession
from uavlogviewer.tools.plotly_exporter import (
    get_series_data_and_timestamps,
    filter_by_segment,
    resolve_session,
    get_aligned_series
)


def get_plotted_messages_and_fields(chart_store: ChartStore) -> Tuple[List[str], List[str]]:
    """
    Extracts all unique field names plotted across all timeseries and scatter charts,
    and returns a tuple of (unique_message_types, unique_fields).
    """
    if not chart_store:
        return [], []

    fields: List[str] = []
    messages: List[str] = []

    for c in chart_store.charts:
        if c.chart_type == "timeseries":
            for expr in c.expressions:
                if expr.name and expr.name not in fields:
                    fields.append(expr.name)
        elif c.chart_type == "scatter":
            for p in c.pairs:
                if p.x_field and p.x_field not in fields:
                    fields.append(p.x_field)
                if p.y_field and p.y_field not in fields:
                    fields.append(p.y_field)

    for f in fields:
        msg_type = f.split('.')[0] if '.' in f else f
        if msg_type not in messages:
            messages.append(msg_type)

    return messages, fields


def get_all_fields_for_messages(parsed_log: ParsedLog, message_types: List[str]) -> List[str]:
    """
    Retrieves all available fields in the log for the given message types.
    """
    if not parsed_log:
        return []

    fields: List[str] = []
    for msg in message_types:
        if parsed_log.field_tree and msg in parsed_log.field_tree:
            for f in parsed_log.field_tree[msg]:
                key = f"{msg}.{f}" if msg != "CALC" else f
                if key not in fields:
                    fields.append(key)
        else:
            # Fallback scan in time_series
            prefix = f"{msg}."
            for k in parsed_log.time_series.keys():
                if k.startswith(prefix) or k == msg:
                    if k not in fields:
                        fields.append(k)

    return fields


def export_plotted_data_to_dataframe(
    parsed_log: Any,
    chart_store: ChartStore,
    scope: str = "plotted_fields",
    time_range: Optional[Tuple[float, float]] = None,
    segment_filter: str = "all",
    fill_mode: str = "none"
) -> pd.DataFrame:
    """
    Constructs a merged pandas DataFrame containing the plotted messages / fields.

    Parameters:
        parsed_log: LogSession or ParsedLog containing time series data.
        chart_store: ChartStore containing active chart panels and expressions.
        scope: "plotted_fields" (default) or "full_messages".
        time_range: Optional (x0, x1) float tuple to slice the exported time range.
        segment_filter: Segment filter mode ("all", "longest", or segment index string).
        fill_mode: "none" (default, keeps NaN/blank for unsampled epochs) or "ffill" (forward-fill).

    Returns:
        pd.DataFrame with 'timestamp' as the first column, followed by telemetry field columns.
    """
    session = resolve_session(parsed_log)
    if not session or not chart_store:
        return pd.DataFrame()

    plotted_items = chart_store.get_plotted_items()
    if not plotted_items:
        return pd.DataFrame()

    # Collect targets: list of (field_name, log_id, col_name)
    target_items: List[Tuple[str, Optional[int], str]] = []

    if scope == "full_messages":
        # Group messages by log_id
        msgs_by_log: Dict[Optional[int], set] = {}
        for f, lid in plotted_items:
            msg = f.split(".")[0]
            msgs_by_log.setdefault(lid, set()).add(msg)

        for lid, msgs in msgs_by_log.items():
            loaded = session.get(lid)
            if not loaded or not loaded.parsed:
                continue
            all_fields = get_all_fields_for_messages(loaded.parsed, list(msgs))
            # Also keep any custom plotted fields
            for f, item_lid in plotted_items:
                if item_lid == lid and f not in all_fields:
                    all_fields.append(f)
            for f in all_fields:
                col_name = f"{loaded.label}.{f}" if session.is_multi else f
                target_items.append((f, lid, col_name))
    else:
        for f, lid in plotted_items:
            loaded = session.get(lid)
            lbl = loaded.label if loaded else "F1"
            col_name = f"{lbl}.{f}" if session.is_multi else f
            target_items.append((f, lid, col_name))

    if not target_items:
        return pd.DataFrame()

    series_dict: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    valid_t_arrays: List[np.ndarray] = []

    for f, lid, col_name in target_items:
        t_arr, y_arr = get_aligned_series(session, f, log_id=lid, segment_filter=segment_filter)
        if len(y_arr) == 0:
            continue

        # Apply visible time range filtering (time_range is in aligned time)
        if time_range is not None and len(t_arr) > 0:
            x0, x1 = time_range
            mask = (t_arr >= x0) & (t_arr <= x1)
            t_arr = t_arr[mask]
            y_arr = y_arr[mask]

        if len(t_arr) > 0:
            series_dict[col_name] = (t_arr, y_arr)
            valid_t_arrays.append(t_arr)

    if not series_dict or not valid_t_arrays:
        return pd.DataFrame()

    # Fast-path: If all series have identical timestamps, construct directly
    first_t = valid_t_arrays[0]
    all_same_t = True
    for t_arr in valid_t_arrays[1:]:
        if len(t_arr) != len(first_t) or not np.array_equal(t_arr, first_t):
            all_same_t = False
            break

    if all_same_t:
        data: Dict[str, Any] = {"timestamp": first_t}
        for col_name, (_, y_arr) in series_dict.items():
            data[col_name] = y_arr
        return pd.DataFrame(data)

    # Multi-rate alignment: union of unique sorted timestamps (rounded to 6 decimals / microsecond precision)
    rounded_t_arrays = [np.round(t, 6) for t in valid_t_arrays]
    union_t = np.sort(np.unique(np.concatenate(rounded_t_arrays)))
    df = pd.DataFrame(index=union_t)
    df.index.name = "timestamp"

    for (col_name, (t_arr, y_arr)), t_rounded in zip(series_dict.items(), rounded_t_arrays):
        s = pd.Series(y_arr, index=t_rounded)
        if s.index.has_duplicates:
            s = s[~s.index.duplicated(keep="first")]
        df[col_name] = s

    if fill_mode == "ffill":
        df = df.ffill()

    return df.reset_index()


def export_plotted_data_to_csv(
    parsed_log: Any,
    chart_store: ChartStore,
    filepath: str,
    scope: str = "plotted_fields",
    time_range: Optional[Tuple[float, float]] = None,
    segment_filter: str = "all",
    fill_mode: str = "none"
) -> int:
    """
    Exports plotted messages/fields to a CSV file.

    Returns:
        Number of rows written to the CSV file.
    """
    df = export_plotted_data_to_dataframe(
        parsed_log=parsed_log,
        chart_store=chart_store,
        scope=scope,
        time_range=time_range,
        segment_filter=segment_filter,
        fill_mode=fill_mode
    )

    if df.empty:
        # Write empty CSV with at least timestamp column
        pd.DataFrame(columns=["timestamp"]).to_csv(filepath, index=False)
        return 0

    df.to_csv(filepath, index=False)
    return len(df)
