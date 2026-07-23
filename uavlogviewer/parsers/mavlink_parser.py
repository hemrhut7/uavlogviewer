"""
mavlink_parser.py — Parser for MAVLink telemetry (.tlog) files.

Dependencies: pymavlink.mavutil, numpy, base_parser.
"""
import os
import numpy as np
from typing import Dict, List, Any
from pymavlink import mavutil
from uavlogviewer.parsers.base_parser import BaseParser, ParsedLog, FlightModeSpan, LogEvent, MODE_COLORS, is_valid_instance_column

class MavlinkParser(BaseParser):
    def parse(self, filepath: str) -> ParsedLog:
        parsed = ParsedLog(
            filename=os.path.basename(filepath),
            log_type="tlog"
        )
        
        try:
            mlog = mavutil.mavlink_connection(filepath)
        except Exception as e:
            print(f"Error opening MAVLink tlog {filepath}: {e}")
            return parsed

        raw_data: Dict[str, Dict[str, list]] = {}
        raw_times: Dict[str, list] = {}
        flight_mode_events = []
        last_mode = None

        while True:
            m = mlog.recv_msg()
            if m is None:
                break

            mtype = m.get_type()
            if mtype == 'BAD_DATA':
                continue

            t = getattr(m, '_timestamp', 0.0)

            if mtype == 'PARAM_VALUE':
                try:
                    pname = m.param_id
                    if isinstance(pname, bytes):
                        pname = pname.decode('utf-8', errors='ignore').rstrip('\x00')
                    parsed.params[pname] = m.param_value
                except Exception:
                    pass
                continue

            elif mtype == 'STATUSTEXT':
                try:
                    txt = m.text
                    if isinstance(txt, bytes):
                        txt = txt.decode('utf-8', errors='ignore')
                    parsed.text_messages.append({'time': t, 'text': txt})
                    parsed.events.append(LogEvent(time=t, name=f"MSG: {txt}", event_type="INFO"))
                except Exception:
                    pass

            elif mtype == 'HEARTBEAT':
                try:
                    mode_str = mavutil.mode_string_v10(m)
                    if mode_str != last_mode:
                        last_mode = mode_str
                        flight_mode_events.append((t, mode_str))
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
            t_list = raw_times[mtype]
            inst_col = None
            for c in ('C', 'I', 'Instance', 'instance', 'Inst', 'Core', 'Id', 'ID', 'id', 'sensor_id', 'Num'):
                if c in field_dict:
                    if is_valid_instance_column(mtype, c, field_dict[c]):
                        inst_col = c
                        break

            if inst_col is not None:
                inst_arr = np.array(field_dict[inst_col])
                unique_insts = np.unique(inst_arr)
                for inst_val in unique_insts:
                    try:
                        val_float = float(inst_val)
                        if val_float.is_integer():
                            inst_str = f"[{int(val_float)}]"
                        else:
                            inst_str = f"[{val_float}]"
                    except (ValueError, TypeError):
                        inst_str = f"[{inst_val}]"
                    sub_mtype = f"{mtype}{inst_str}"

                    mask = (inst_arr == inst_val)
                    sub_t_arr = np.array(t_list, dtype=np.float64)[mask]
                    parsed.timestamps[sub_mtype] = sub_t_arr
                    parsed.field_tree[sub_mtype] = list(field_dict.keys())

                    for f, val_list in field_dict.items():
                        key = f"{sub_mtype}.{f}"
                        try:
                            parsed.time_series[key] = np.array(val_list)[mask]
                        except Exception:
                            pass
            else:
                t_arr = np.array(t_list, dtype=np.float64)
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
                t1 = flight_mode_events[i + 1][0] if i + 1 < len(flight_mode_events) else t0 + 1.0
                color = MODE_COLORS.get(mode_name.upper(), "#CCCCCC")
                parsed.flight_modes.append(FlightModeSpan(name=str(mode_name), start_time=t0, end_time=t1, color=color))

        return parsed
