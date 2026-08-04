"""
mavlink_parser.py — Ultra-fast parallel parser for MAVLink telemetry (.tlog) files
using ProcessPoolExecutor + chunk boundary alignment + automatic unit conversions (rad -> deg, degE7 -> deg, mm -> m, cm/s -> m/s).

Dependencies: pymavlink.mavutil, numpy, base_parser.
"""
import os
import struct
import numpy as np
from typing import Dict, List, Any, Tuple
from concurrent.futures import ProcessPoolExecutor
from pymavlink import mavutil
from uavlogviewer.parsers.base_parser import BaseParser, ParsedLog, FlightModeSpan, LogEvent, MODE_COLORS, is_valid_instance_column

def apply_mavlink_unit_conversions(mtype: str, field_name: str, arr: np.ndarray) -> np.ndarray:
    """Applies standard MAVLink unit conversions (rad->deg, 1e7 deg->deg, mm->m, cm/s->m/s)."""
    if arr is None or len(arr) == 0:
        return arr

    base_mtype = mtype.split('[')[0].upper()
    field_lower = field_name.lower()

    # 1. Attitude Angles: rad -> deg
    if base_mtype in ('ATTITUDE', 'HIGHRES_IMU') and field_lower in ('roll', 'pitch', 'yaw'):
        abs_max = float(np.nanmax(np.abs(arr))) if len(arr) > 0 else 0
        if abs_max <= 7.0:  # ~2*pi radians
            return np.degrees(arr)

    # 2. Latitude & Longitude: 1e7 int -> deg
    if field_lower in ('lat', 'lon', 'latitude', 'longitude', 'lat_int', 'lon_int'):
        abs_max = float(np.nanmax(np.abs(arr))) if len(arr) > 0 else 0
        if abs_max > 180.0:  # Integer scaled by 1e7
            return arr / 1e7

    # 3. Altitude: mm -> meters
    if base_mtype in ('GLOBAL_POSITION_INT', 'GPS_RAW_INT', 'GPS2_RAW', 'GPS_INPUT', 'POSITION_TARGET_GLOBAL_INT', 'HOME_POSITION'):
        if field_lower in ('alt', 'relative_alt'):
            abs_max = float(np.nanmax(np.abs(arr))) if len(arr) > 0 else 0
            if abs_max > 5000.0 or np.mean(np.abs(arr)) > 1000.0:  # In mm
                return arr / 1000.0

        if field_lower in ('vx', 'vy', 'vz', 'vel'):
            return arr / 100.0

    return arr

def find_tlog_chunk_boundary(filename: str, target_ofs: int, file_size: int) -> int:
    """Finds exact packet boundary near target_ofs by searching for STX and verifying 8-byte timestamp header."""
    if target_ofs <= 0:
        return 0
    if target_ofs >= file_size:
        return file_size

    try:
        with open(filename, 'rb') as f:
            f.seek(target_ofs)
            buf = f.read(8192)

        for idx in range(len(buf) - 9):
            if buf[idx] in (0xFD, 0xFE):  # MAVLink v2 (0xFD) or v1 (0xFE) STX
                if idx >= 8:
                    tbuf = buf[idx - 8:idx]
                    tusec = struct.unpack('>Q', tbuf)[0]
                    if 1e14 < tusec < 3e15:  # Valid microsecond timestamp between 1970 and 2060
                        return target_ofs + idx - 8
    except Exception:
        pass

    return target_ofs

def _parse_tlog_chunk_worker(filepath: str, start_byte: int, end_byte: int) -> Tuple[Dict, Dict, set, Dict, List, List, List]:
    """Parallel worker unpacking a byte chunk [start_byte, end_byte] of a .tlog file."""
    raw_data: Dict[Any, Dict[str, list]] = {}
    raw_times: Dict[Any, list] = {}
    cache: Dict[Any, tuple] = {}
    all_sysids = set()
    params: Dict[str, Any] = {}
    text_messages: List[Dict[str, Any]] = []
    events: List[Tuple[float, str, str]] = []
    flight_mode_events: List[Tuple[float, str]] = []

    try:
        mlog = mavutil.mavlogfile(filepath, notimestamps=False)
        if start_byte > 0:
            _ = mlog.recv_msg()  # Auto-detect MAVLink wire protocol version at offset 0
            mlog.f.seek(start_byte)

        last_mode = None

        while mlog.f.tell() < end_byte:
            m = mlog.recv_msg()
            if m is None:
                break

            mtype = getattr(m, '_type', None) or m.get_type()
            if mtype == 'BAD_DATA':
                continue

            t = getattr(m, '_timestamp', 0.0)
            hdr = getattr(m, '_header', None)
            sysid = hdr.srcSystem if hdr else (m.get_srcSystem() if hasattr(m, 'get_srcSystem') else 1)
            all_sysids.add(sysid)

            if mtype == 'PARAM_VALUE':
                try:
                    pname = m.param_id
                    if isinstance(pname, bytes):
                        pname = pname.decode('utf-8', errors='ignore').rstrip('\x00')
                    params[pname] = m.param_value
                except Exception:
                    pass
                continue

            elif mtype == 'STATUSTEXT':
                try:
                    txt = m.text
                    if isinstance(txt, bytes):
                        txt = txt.decode('utf-8', errors='ignore')
                    text_messages.append({'time': t, 'text': txt})
                    events.append((t, f"MSG: {txt}", "INFO"))
                except Exception:
                    pass

            elif mtype == 'HEARTBEAT':
                try:
                    if sysid == 1:
                        mode_str = mavutil.mode_string_v10(m)
                        if mode_str and mode_str != last_mode and not mode_str.startswith("Mode("):
                            last_mode = mode_str
                            flight_mode_events.append((t, mode_str))
                except Exception:
                    pass

            msg_key = (sysid, mtype)
            if msg_key not in cache:
                fields = getattr(m, '_fieldnames', None) or m.get_fieldnames()
                if not fields:
                    continue
                f_dict = {f: [] for f in fields}
                t_list = []
                raw_data[msg_key] = f_dict
                raw_times[msg_key] = t_list
                cache[msg_key] = (t_list, f_dict, fields)

            t_list, f_dict, fields = cache[msg_key]
            t_list.append(t)
            m_dict = m.__dict__
            for f in fields:
                f_dict[f].append(m_dict.get(f, 0.0))

        if hasattr(mlog, 'close'):
            mlog.close()
    except Exception as e:
        print(f"Worker error parsing chunk [{start_byte}:{end_byte}]: {e}")

    return raw_data, raw_times, all_sysids, params, text_messages, events, flight_mode_events

class MavlinkParser(BaseParser):
    def parse(self, filepath: str) -> ParsedLog:
        parsed = ParsedLog(
            filename=os.path.basename(filepath),
            log_type="tlog"
        )

        if not os.path.exists(filepath):
            return parsed

        file_size = os.path.getsize(filepath)
        cpu_count = os.cpu_count() or 4
        num_workers = max(1, min(cpu_count, 8))

        # Use single-process parsing for small files (< 2MB) or single CPU
        if file_size < 2_000_000 or num_workers <= 1:
            raw_data, raw_times, all_sysids, params, text_msgs, events_list, mode_events = _parse_tlog_chunk_worker(
                filepath, 0, file_size
            )
            parsed.params.update(params)
            parsed.text_messages.extend(text_msgs)
            for t_val, e_name, e_type in events_list:
                parsed.events.append(LogEvent(time=t_val, name=e_name, event_type=e_type))
            flight_mode_events = mode_events
        else:
            # Parallel Multi-Processing Chunk Parsing
            chunk_size = file_size // num_workers
            boundaries = [0]
            for i in range(1, num_workers):
                boundaries.append(find_tlog_chunk_boundary(filepath, i * chunk_size, file_size))
            boundaries.append(file_size)

            futures = []
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                for i in range(len(boundaries) - 1):
                    s, e = boundaries[i], boundaries[i + 1]
                    if s < e:
                        futures.append(executor.submit(_parse_tlog_chunk_worker, filepath, s, e))

            res_list = [f.result() for f in futures]

            # Merge results from worker processes
            raw_data: Dict[Any, Dict[str, list]] = {}
            raw_times: Dict[Any, list] = {}
            all_sysids = set()
            flight_mode_events = []

            for r_data, r_times, r_sysids, r_params, r_text, r_events, r_modes in res_list:
                parsed.params.update(r_params)
                parsed.text_messages.extend(r_text)
                for t_val, e_name, e_type in r_events:
                    parsed.events.append(LogEvent(time=t_val, name=e_name, event_type=e_type))
                flight_mode_events.extend(r_modes)
                all_sysids.update(r_sysids)

                for msg_key, f_dict in r_data.items():
                    if msg_key not in raw_data:
                        raw_data[msg_key] = {f: [] for f in f_dict.keys()}
                        raw_times[msg_key] = []
                    
                    raw_times[msg_key].extend(r_times[msg_key])
                    for f, val_list in f_dict.items():
                        raw_data[msg_key][f].extend(val_list)

        has_multiple_sysids = len({s for s in all_sysids if s != 0}) > 1

        for (sysid, mtype), field_dict in raw_data.items():
            if has_multiple_sysids:
                sys_mtype = f"{mtype}[S{sysid}]"
            else:
                sys_mtype = mtype

            t_list = raw_times[(sysid, mtype)]
            if not t_list:
                continue

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
                    sub_mtype = f"{sys_mtype}{inst_str}"

                    mask = (inst_arr == inst_val)
                    sub_t_arr = np.array(t_list, dtype=np.float64)[mask]
                    parsed.timestamps[sub_mtype] = sub_t_arr
                    parsed.field_tree[sub_mtype] = list(field_dict.keys())

                    for f, val_list in field_dict.items():
                        key = f"{sub_mtype}.{f}"
                        try:
                            arr = np.array(val_list, dtype=np.float64)[mask]
                            arr = apply_mavlink_unit_conversions(sub_mtype, f, arr)
                            parsed.time_series[key] = arr
                        except Exception:
                            pass
            else:
                t_arr = np.array(t_list, dtype=np.float64)
                parsed.timestamps[sys_mtype] = t_arr
                parsed.field_tree[sys_mtype] = list(field_dict.keys())

                for f, val_list in field_dict.items():
                    key = f"{sys_mtype}.{f}"
                    try:
                        arr = np.array(val_list, dtype=np.float64)
                        arr = apply_mavlink_unit_conversions(sys_mtype, f, arr)
                        parsed.time_series[key] = arr
                    except Exception:
                        pass

        # Sort and build flight mode intervals
        if flight_mode_events:
            flight_mode_events.sort(key=lambda x: x[0])
            for i in range(len(flight_mode_events)):
                t0, mode_name = flight_mode_events[i]
                t1 = flight_mode_events[i + 1][0] if i + 1 < len(flight_mode_events) else t0 + 10.0
                color = MODE_COLORS.get(str(mode_name).upper(), "#CCCCCC")
                parsed.flight_modes.append(FlightModeSpan(name=str(mode_name), start_time=t0, end_time=t1, color=color))

        return parsed
