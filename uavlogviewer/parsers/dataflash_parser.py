"""
dataflash_parser.py — Ultra-fast parser for ArduPilot DataFlash binary (.bin) and text (.log) files.

Leverages parallel mmap unpacking via fast_log_reader for 10x-30x speedups on .bin files.

Dependencies: pymavlink, numpy, pandas, base_parser, fast_log_reader.
"""
import mmap
import struct
import sys
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from pymavlink import DFReader, mavutil
from uavlogviewer.parsers.base_parser import (
    BaseParser,
    ParsedLog,
    FlightModeSpan,
    LogEvent,
    MODE_COLORS,
    get_flight_mode_info,
    is_valid_instance_column,
    LazyTimeSeriesDict,
    LazyTimestampsDict,
)
from uavlogviewer.parsers.fast_log_reader import parse_bin_log


INSTANCE_CANDIDATE_COLUMNS = ('C', 'I', 'Instance', 'instance', 'Inst', 'Core', 'Id', 'ID', 'Num')


def _clean_str(val: Any) -> str:
    """Decodes bytes to utf-8 and strips trailing null padding bytes from struct-unpacked strings."""
    if isinstance(val, (bytes, bytearray)):
        return val.decode('utf-8', errors='replace').rstrip('\x00').strip()
    return str(val).rstrip('\x00').strip()


class SilenceStderr:
    """Context manager to suppress C/Python-level stderr during noisy pymavlink scanning."""
    def __enter__(self):
        self.active = False
        self.null_fd = None
        self.orig_fd2 = None
        try:
            sys.stderr.flush()
            self.null_fd = os.open(os.devnull, os.O_RDWR)
            self.orig_fd2 = os.dup(2)
            os.dup2(self.null_fd, 2)
            self.active = True
        except Exception:
            if self.orig_fd2 is not None:
                try:
                    os.close(self.orig_fd2)
                except Exception:
                    pass
            if self.null_fd is not None:
                try:
                    os.close(self.null_fd)
                except Exception:
                    pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.active:
            try:
                os.dup2(self.orig_fd2, 2)
                os.close(self.orig_fd2)
                os.close(self.null_fd)
            except Exception:
                pass


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
        file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        if file_size == 0:
            return parsed

        try:
            with SilenceStderr():
                mlog = mavutil.mavlink_connection(filepath)
        except Exception as e:
            print(f"Error opening MAVLink connection for {filepath}: {e}")
            return parsed

        field_tree = {}
        instances_by_type = {}
        end_timestamp = 0.0

        with open(filepath, 'rb') as f:
            with mmap.mmap(f.fileno(), file_size, access=mmap.ACCESS_READ) as mm:
                for tname, tid in mlog.name_to_id.items():
                    fmt = mlog.formats.get(tid)
                    if not fmt:
                        continue
                    cols = fmt.columns
                    offsets = mlog.offsets[tid] if tid < len(mlog.offsets) else []
                    if len(offsets) == 0:
                        continue

                    time_col = None
                    for c in ['TimeUS', 'time_us', 'TimeMS', 'Time']:
                        if c in cols:
                            time_col = c
                            break

                    inst_col = None
                    inst_idx = -1
                    for c in INSTANCE_CANDIDATE_COLUMNS:
                        if c in cols and c != time_col:
                            inst_col = c
                            inst_idx = cols.index(c)
                            break

                    is_inst = False
                    unique_insts = []
                    if inst_col is not None and inst_idx >= 0:
                        s = struct.Struct(fmt.msg_struct)
                        step = max(1, len(offsets) // 200)
                        sample_offsets = offsets[::step][:200]
                        sample_vals = []
                        for ofs in sample_offsets:
                            ofs_int = int(ofs)
                            if ofs_int + 3 + s.size <= file_size:
                                sample_vals.append(s.unpack_from(mm, ofs_int + 3)[inst_idx])

                        if sample_vals and is_valid_instance_column(tname, inst_col, sample_vals):
                            is_inst = True
                            unique_insts = sorted(list(set(sample_vals)))

                    if is_inst and unique_insts:
                        instances_by_type[tname] = (inst_col, unique_insts)
                        fields = [c for c in cols if c != time_col]
                        for u in unique_insts:
                            try:
                                u_f = float(u)
                                inst_str = f"[{int(u_f)}]" if u_f.is_integer() else f"[{u_f}]"
                            except (ValueError, TypeError):
                                inst_str = f"[{u}]"
                            field_tree[f"{tname}{inst_str}"] = fields
                    else:
                        fields = [c for c in cols if c != time_col]
                        field_tree[tname] = fields

                # Quick duration check from most frequent message with TimeUS
                total_duration = 0.0
                for candidate_type in ['ATT', 'IMU', 'XKF1', 'POS', 'GPS', 'MODE']:
                    cid = mlog.name_to_id.get(candidate_type)
                    if cid is not None and cid < len(mlog.offsets) and len(mlog.offsets[cid]) > 1:
                        fmt = mlog.formats[cid]
                        if 'TimeUS' in fmt.columns:
                            time_idx = fmt.columns.index('TimeUS')
                            s = struct.Struct(fmt.msg_struct)
                            first_ofs = mlog.offsets[cid][0]
                            last_ofs = mlog.offsets[cid][-1]
                            if first_ofs + 3 + s.size <= file_size and last_ofs + 3 + s.size <= file_size:
                                t0 = s.unpack_from(mm, first_ofs + 3)[time_idx] / 1e6
                                t1 = s.unpack_from(mm, last_ofs + 3)[time_idx] / 1e6
                                if t1 > t0:
                                    total_duration = t1 - t0
                                    end_timestamp = t1
                                    break

        parsed.field_tree = field_tree
        parsed.total_log_duration = total_duration

        # Compute estimated rates for all types in field_tree
        if total_duration > 0:
            for tname, tid in mlog.name_to_id.items():
                if tid < len(mlog.offsets):
                    count = len(mlog.offsets[tid])
                    if count > 1:
                        if tname in instances_by_type:
                            inst_col, u_insts = instances_by_type[tname]
                            rate = (count / max(1, len(u_insts))) / total_duration
                            for u in u_insts:
                                try:
                                    u_f = float(u)
                                    inst_str = f"[{int(u_f)}]" if u_f.is_integer() else f"[{u_f}]"
                                except (ValueError, TypeError):
                                    inst_str = f"[{u}]"
                                parsed.estimated_rates[f"{tname}{inst_str}"] = rate
                        else:
                            parsed.estimated_rates[tname] = count / total_duration

        # Compact mlog.offsets into numpy arrays to reduce memory footprint
        for tid in range(len(mlog.offsets)):
            if len(mlog.offsets[tid]) > 0 and not isinstance(mlog.offsets[tid], np.ndarray):
                mlog.offsets[tid] = np.array(mlog.offsets[tid], dtype=np.uint64)

        unpacked_types = set()

        def unpack_target_type(target_type: str):
            base_mtype = target_type.split('[')[0]
            if base_mtype in unpacked_types:
                return
            unpacked_types.add(base_mtype)

            dfs = parse_bin_log(filepath, [base_mtype], ignore_gps_clock=True, mlog=mlog)
            if base_mtype not in dfs or dfs[base_mtype].empty:
                return

            df = dfs[base_mtype]
            time_col = None
            for c in ['TimeUS', 'time_us', 'TimeMS', 'Time']:
                if c in df.columns:
                    time_col = c
                    break

            inst_col = None
            for c in INSTANCE_CANDIDATE_COLUMNS:
                if c in df.columns and c != time_col:
                    if is_valid_instance_column(base_mtype, c, df[c].to_numpy()):
                        inst_col = c
                        break

            if inst_col is not None:
                unique_insts = df[inst_col].unique()
                for inst_val in unique_insts:
                    sub_df = df[df[inst_col] == inst_val]
                    if sub_df.empty:
                        continue
                    try:
                        val_float = float(inst_val)
                        inst_str = f"[{int(val_float)}]" if val_float.is_integer() else f"[{val_float}]"
                    except (ValueError, TypeError):
                        inst_str = f"[{inst_val}]"
                    sub_mtype = f"{base_mtype}{inst_str}"

                    if time_col:
                        t_arr = sub_df[time_col].to_numpy(dtype=np.float64)
                        if 'US' in time_col or 'us' in time_col:
                            t_arr /= 1e6
                        elif 'MS' in time_col or 'ms' in time_col:
                            t_arr /= 1e3
                    else:
                        t_arr = np.arange(len(sub_df), dtype=np.float64)

                    parsed.timestamps[sub_mtype] = t_arr
                    fields = [col for col in sub_df.columns if col != time_col]
                    if sub_mtype not in parsed.field_tree:
                        parsed.field_tree[sub_mtype] = fields

                    for f in fields:
                        key = f"{sub_mtype}.{f}"
                        parsed.time_series[key] = sub_df[f].to_numpy()
            else:
                if time_col:
                    t_arr = df[time_col].to_numpy(dtype=np.float64)
                    if 'US' in time_col or 'us' in time_col:
                        t_arr /= 1e6
                    elif 'MS' in time_col or 'ms' in time_col:
                        t_arr /= 1e3
                else:
                    t_arr = np.arange(len(df), dtype=np.float64)

                parsed.timestamps[base_mtype] = t_arr
                fields = [col for col in df.columns if col != time_col]
                if base_mtype not in parsed.field_tree:
                    parsed.field_tree[base_mtype] = fields

                for f in fields:
                    key = f"{base_mtype}.{f}"
                    parsed.time_series[key] = df[f].to_numpy()

        # Wire lazy dicts
        parsed.time_series = LazyTimeSeriesDict(parsed, loader=unpack_target_type)
        parsed.timestamps = LazyTimestampsDict(parsed, loader=unpack_target_type)

        # Unpack key metadata types upfront (PARM, MSG, EV, MODE, STAT, GPS)
        meta_types = [t for t in ['PARM', 'MSG', 'EV', 'MODE', 'STAT', 'GPS'] if t in mlog.name_to_id]
        if meta_types:
            dfs_meta = parse_bin_log(filepath, meta_types, ignore_gps_clock=True, mlog=mlog)

            if 'PARM' in dfs_meta and not dfs_meta['PARM'].empty:
                df_parm = dfs_meta['PARM']
                for _, row in df_parm.iterrows():
                    pname = _clean_str(row.get('Name', row.get('Param_Name', '')))
                    pval = row.get('Value', row.get('Param_Value', 0.0))
                    if pname:
                        parsed.params[pname] = pval

            if 'MSG' in dfs_meta and not dfs_meta['MSG'].empty:
                df_msg = dfs_meta['MSG']
                time_col = 'TimeUS' if 'TimeUS' in df_msg.columns else ('time_us' if 'time_us' in df_msg.columns else None)
                for _, row in df_msg.iterrows():
                    t = (row[time_col] / 1e6) if time_col and pd.notnull(row[time_col]) else 0.0
                    txt = _clean_str(row.get('Message', row.get('Text', '')))
                    parsed.text_messages.append({'time': t, 'text': txt})

            if 'EV' in dfs_meta and not dfs_meta['EV'].empty:
                df_ev = dfs_meta['EV']
                time_col = 'TimeUS' if 'TimeUS' in df_ev.columns else ('time_us' if 'time_us' in df_ev.columns else None)
                for _, row in df_ev.iterrows():
                    t = (row[time_col] / 1e6) if time_col and pd.notnull(row[time_col]) else 0.0
                    ev_id = _clean_str(row.get('Id', row.get('Event', '')))
                    parsed.events.append(LogEvent(time=t, name=f"EV: {ev_id}", event_type="EVENT"))

            if 'MODE' in dfs_meta and not dfs_meta['MODE'].empty:
                df_mode = dfs_meta['MODE']
                time_col = 'TimeUS' if 'TimeUS' in df_mode.columns else ('time_us' if 'time_us' in df_mode.columns else None)
                flight_mode_events = []
                for _, row in df_mode.iterrows():
                    t = (row[time_col] / 1e6) if time_col and pd.notnull(row[time_col]) else 0.0
                    m_str = _clean_str(row.get('Mode', row.get('ModeNum', 'UNKNOWN')))
                    flight_mode_events.append((t, m_str))

                for i in range(len(flight_mode_events)):
                    t0, mode_raw = flight_mode_events[i]
                    t1 = flight_mode_events[i + 1][0] if i + 1 < len(flight_mode_events) else max(end_timestamp, t0 + 1.0)
                    mode_name, color = get_flight_mode_info(mode_raw)
                    parsed.flight_modes.append(FlightModeSpan(name=mode_name, start_time=t0, end_time=t1, color=color))

            # Populate metadata series into parsed (e.g. GPS, STAT)
            for mtype in ['STAT', 'GPS']:
                if mtype in dfs_meta and not dfs_meta[mtype].empty:
                    df = dfs_meta[mtype]
                    unpacked_types.add(mtype)
                    time_col = 'TimeUS' if 'TimeUS' in df.columns else ('time_us' if 'time_us' in df.columns else None)
                    t_arr = (df[time_col].to_numpy(dtype=np.float64) / 1e6) if time_col else np.arange(len(df), dtype=np.float64)
                    
                    inst_col = 'I' if 'I' in df.columns and is_valid_instance_column(mtype, 'I', df['I'].to_numpy()) else None
                    if inst_col:
                        for u_val in df[inst_col].unique():
                            sub_df = df[df[inst_col] == u_val]
                            try:
                                u_f = float(u_val)
                                inst_str = f"[{int(u_f)}]" if u_f.is_integer() else f"[{u_f}]"
                            except Exception:
                                inst_str = f"[{u_val}]"
                            sub_mtype = f"{mtype}{inst_str}"
                            sub_t = (sub_df[time_col].to_numpy(dtype=np.float64) / 1e6) if time_col else np.arange(len(sub_df), dtype=np.float64)
                            parsed.timestamps[sub_mtype] = sub_t
                            for col in sub_df.columns:
                                if col != time_col:
                                    parsed.time_series[f"{sub_mtype}.{col}"] = sub_df[col].to_numpy()
                    else:
                        parsed.timestamps[mtype] = t_arr
                        for col in df.columns:
                            if col != time_col:
                                parsed.time_series[f"{mtype}.{col}"] = df[col].to_numpy()

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
            t_list = raw_times[mtype]
            inst_col = None
            for c in ('C', 'I', 'Instance', 'instance', 'Inst', 'Core', 'Id', 'ID', 'Num'):
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
                t1 = flight_mode_events[i + 1][0] if i + 1 < len(flight_mode_events) else max(last_timestamp, t0 + 1.0)
                color = MODE_COLORS.get(mode_name.upper(), "#CCCCCC")
                parsed.flight_modes.append(FlightModeSpan(name=str(mode_name), start_time=t0, end_time=t1, color=color))

        return parsed
