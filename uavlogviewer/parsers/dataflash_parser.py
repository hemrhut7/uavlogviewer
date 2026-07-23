"""
dataflash_parser.py — Ultra-fast parser for ArduPilot DataFlash binary (.bin) and text (.log) files.

Leverages parallel mmap unpacking via fast_log_reader for 10x-30x speedups on .bin files.

Dependencies: pymavlink, numpy, pandas, base_parser, fast_log_reader.
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from pymavlink import DFReader, mavutil
from uavlogviewer.parsers.base_parser import BaseParser, ParsedLog, FlightModeSpan, LogEvent, MODE_COLORS, get_flight_mode_info
from uavlogviewer.parsers.fast_log_reader import parse_bin_log

def is_binary_log(filepath: str) -> bool:
    if filepath.lower().endswith('.bin'):
        return True
    try:
        with open(filepath, 'rb') as f:
            header = f.read(2)
            return header == b'\xa3\x95'
    except Exception:
        return False

class DataflashParser(BaseParser):
    def parse(self, filepath: str) -> ParsedLog:
        parsed = ParsedLog(
            filename=os.path.basename(filepath),
            log_type="dataflash"
        )
        
        if is_binary_log(filepath):
            return self._parse_binary_fast(filepath, parsed)
        else:
            return self._parse_text(filepath, parsed)

    def _parse_binary_fast(self, filepath: str, parsed: ParsedLog) -> ParsedLog:
        try:
            mlog = mavutil.mavlink_connection(filepath)
            all_types = list(mlog.name_to_id.keys())
        except Exception as e:
            print(f"Error opening MAVLink connection for {filepath}: {e}")
            return parsed

        # Fast parallel mmap parse
        dfs = parse_bin_log(filepath, all_types, ignore_gps_clock="auto")

        # Process PARM
        if 'PARM' in dfs and not dfs['PARM'].empty:
            df_parm = dfs['PARM']
            for _, row in df_parm.iterrows():
                pname = str(row.get('Name', row.get('Param_Name', '')))
                pval = row.get('Value', row.get('Param_Value', 0.0))
                if pname:
                    parsed.params[pname] = pval

        # Process MSG
        if 'MSG' in dfs and not dfs['MSG'].empty:
            df_msg = dfs['MSG']
            time_col = 'TimeUS' if 'TimeUS' in df_msg.columns else ('time_us' if 'time_us' in df_msg.columns else None)
            for _, row in df_msg.iterrows():
                t = (row[time_col] / 1e6) if time_col and pd.notnull(row[time_col]) else 0.0
                txt = str(row.get('Message', row.get('Text', '')))
                parsed.text_messages.append({'time': t, 'text': txt})

        # Process EV (Events)
        if 'EV' in dfs and not dfs['EV'].empty:
            df_ev = dfs['EV']
            time_col = 'TimeUS' if 'TimeUS' in df_ev.columns else ('time_us' if 'time_us' in df_ev.columns else None)
            for _, row in df_ev.iterrows():
                t = (row[time_col] / 1e6) if time_col and pd.notnull(row[time_col]) else 0.0
                ev_id = str(row.get('Id', row.get('Event', '')))
                parsed.events.append(LogEvent(time=t, name=f"EV: {ev_id}", event_type="EVENT"))

        # Process MODE
        last_timestamp = 0.0
        if 'MODE' in dfs and not dfs['MODE'].empty:
            df_mode = dfs['MODE']
            time_col = 'TimeUS' if 'TimeUS' in df_mode.columns else ('time_us' if 'time_us' in df_mode.columns else None)
            flight_mode_events = []
            for _, row in df_mode.iterrows():
                t = (row[time_col] / 1e6) if time_col and pd.notnull(row[time_col]) else 0.0
                m_str = str(row.get('Mode', row.get('ModeNum', 'UNKNOWN')))
                flight_mode_events.append((t, m_str))

            # Build flight mode intervals
            for i in range(len(flight_mode_events)):
                t0, mode_raw = flight_mode_events[i]
                t1 = flight_mode_events[i + 1][0] if i + 1 < len(flight_mode_events) else t0 + 10.0
                mode_name, color = get_flight_mode_info(mode_raw)
                parsed.flight_modes.append(FlightModeSpan(name=mode_name, start_time=t0, end_time=t1, color=color))

        # Store all message series into parsed log
        for mtype, df in dfs.items():
            if df.empty or mtype in ['PARM', 'FMT', 'FMTU']:
                continue

            time_col = None
            for c in ['TimeUS', 'time_us', 'TimeMS', 'Time']:
                if c in df.columns:
                    time_col = c
                    break

            if time_col:
                t_arr = df[time_col].to_numpy(dtype=np.float64)
                if 'US' in time_col or 'us' in time_col:
                    t_arr /= 1e6
                elif 'MS' in time_col or 'ms' in time_col:
                    t_arr /= 1e3
            else:
                t_arr = np.arange(len(df), dtype=np.float64)

            if len(t_arr) > 0:
                last_timestamp = max(last_timestamp, t_arr[-1])

            parsed.timestamps[mtype] = t_arr
            fields = [col for col in df.columns if col != time_col]
            parsed.field_tree[mtype] = fields

            for f in fields:
                key = f"{mtype}.{f}"
                parsed.time_series[key] = df[f].to_numpy()

        # Update last flight mode end time if needed
        if parsed.flight_modes:
            parsed.flight_modes[-1].end_time = max(last_timestamp, parsed.flight_modes[-1].start_time + 1.0)

        return parsed

    def _parse_text(self, filepath: str, parsed: ParsedLog) -> ParsedLog:
        try:
            log = DFReader.DFReader_text(filepath)
        except Exception as e:
            print(f"Error opening text DataFlash log {filepath}: {e}")
            return parsed

        raw_data: Dict[str, Dict[str, list]] = {}
        raw_times: Dict[str, list] = {}
        flight_mode_events = []
        last_timestamp = 0.0

        while True:
            m = log.recv_msg()
            if m is None:
                break
            
            mtype = m.get_type()
            t = getattr(m, '_timestamp', 0.0)
            if t > 0:
                last_timestamp = max(last_timestamp, t)

            if mtype == 'PARM':
                try:
                    pname = m.Name if hasattr(m, 'Name') else str(getattr(m, 'Param_Name', ''))
                    pval = m.Value if hasattr(m, 'Value') else getattr(m, 'Param_Value', 0.0)
                    parsed.params[pname] = pval
                except Exception:
                    pass
                continue

            elif mtype == 'MSG':
                try:
                    txt = getattr(m, 'Message', getattr(m, 'Text', ''))
                    parsed.text_messages.append({'time': t, 'text': txt})
                    parsed.events.append(LogEvent(time=t, name=f"MSG: {txt}", event_type="INFO"))
                except Exception:
                    pass

            elif mtype == 'MODE':
                try:
                    m_str = getattr(m, 'Mode', str(getattr(m, 'ModeNum', 'UNKNOWN')))
                    flight_mode_events.append((t, str(m_str)))
                except Exception:
                    pass

            fields = m.get_fieldnames()
            if not fields:
                continue

            if mtype not in raw_data:
                raw_data[mtype] = {f: [] for f in fields}
                raw_times[mtype] = []

            raw_times[mtype].append(t)
            for f in fields:
                val = getattr(m, f, 0.0)
                raw_data[mtype][f].append(val)

        for mtype, field_dict in raw_data.items():
            t_arr = np.array(raw_times[mtype], dtype=np.float64)
            parsed.timestamps[mtype] = t_arr
            parsed.field_tree[mtype] = list(field_dict.keys())
            
            for f, val_list in field_dict.items():
                key = f"{mtype}.{f}"
                try:
                    parsed.time_series[key] = np.array(val_list)
                except Exception:
                    pass

        if flight_mode_events:
            for i in range(len(flight_mode_events)):
                t0, mode_name = flight_mode_events[i]
                t1 = flight_mode_events[i + 1][0] if i + 1 < len(flight_mode_events) else max(last_timestamp, t0 + 1.0)
                color = MODE_COLORS.get(mode_name.upper(), "#CCCCCC")
                parsed.flight_modes.append(FlightModeSpan(name=str(mode_name), start_time=t0, end_time=t1, color=color))

        return parsed
