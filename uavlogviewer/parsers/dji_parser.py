"""
dji_parser.py — Parser for DJI telemetry logs (.txt / .csv).

Dependencies: pandas, numpy, base_parser.
"""
import os
import pandas as pd
import numpy as np
from uavlogviewer.parsers.base_parser import BaseParser, ParsedLog

class DjiParser(BaseParser):
    def parse(self, filepath: str) -> ParsedLog:
        parsed = ParsedLog(
            filename=os.path.basename(filepath),
            log_type="dji"
        )
        
        try:
            df = pd.read_csv(filepath, low_memory=False)
        except Exception as e:
            print(f"Error reading DJI log {filepath}: {e}")
            return parsed

        if df.empty:
            return parsed

        time_col = None
        for col in ['offsetTime', 'time(millisecond)', 'Tick', 'Time']:
            if col in df.columns:
                time_col = col
                break

        if time_col is None:
            time_arr = np.arange(len(df), dtype=np.float64) * 0.1
        else:
            time_arr = df[time_col].to_numpy(dtype=np.float64)
            if time_arr.max() > 10000.0 and 'millisecond' in time_col.lower():
                time_arr /= 1000.0

        parsed.timestamps['DJI'] = time_arr
        parsed.field_tree['DJI'] = []

        for col in df.columns:
            if col == time_col:
                continue
            series = pd.to_numeric(df[col], errors='coerce').fillna(0.0).to_numpy()
            key = f"DJI.{col}"
            parsed.time_series[key] = series
            parsed.field_tree['DJI'].append(col)

        return parsed
