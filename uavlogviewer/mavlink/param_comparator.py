"""
param_comparator.py — Parameter Comparison, Safe-Guard & Parser Engine.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ParamStatus(Enum):
    MATCH = "Match"
    MODIFIED = "Modified"
    PROTECTED = "Protected"
    MISSING_IN_FC = "Missing in FC"
    EXTRA_IN_FC = "Extra in FC"


# Blacklists for auto safe guard protection
SAFE_GUARD_GROUPS = {
    "BARO1", "BARO2", "BARO3",
    "INS", "INS4", "INS5",
    "STAT"
}

SAFE_GUARD_PREFIXES = (
    "COMPASS_OFS",
    "COMPASS_SCALE",
    "COMPASS_CAL_FIT",
    "ARSPD_OFFSET",
)

SAFE_GUARD_KEYWORDS = (
    "DEVID",
    "DEV_ID",
    "NODEID",
    "_ID"
)


def is_protected_param(param_name: str) -> Tuple[bool, str]:
    """
    Check if a parameter is protected (calibration data or read-only hardware ID).
    Returns (is_protected, reason).
    """
    p_upper = param_name.upper().strip()
    prefix = p_upper.split('_')[0]

    for kw in SAFE_GUARD_KEYWORDS:
        if kw in p_upper:
            return True, "Hardware ID (Read-Only)"

    if prefix in SAFE_GUARD_GROUPS:
        return True, "Sensor Calibration Group"

    for pre in SAFE_GUARD_PREFIXES:
        if p_upper.startswith(pre):
            return True, "Sensor Calibration Offset/Scale"

    return False, ""


@dataclass
class ParamDiffItem:
    name: str
    group: str
    fc_value: Optional[float]
    target_value: Optional[float]
    delta: Optional[float]
    status: ParamStatus
    is_protected: bool
    protection_reason: str
    is_checked: bool


def parse_param_file(filepath: str) -> Dict[str, float]:
    """
    Parses ArduPilot / PX4 .param or .parm files (comma or whitespace separated).
    Ignores comment lines starting with #.
    """
    params = {}
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ',' in line:
                parts = line.split(',')
            else:
                parts = line.split()

            if len(parts) >= 2:
                key = parts[0].strip()
                try:
                    val = float(parts[1].strip())
                    params[key] = val
                except ValueError:
                    pass
    return params


def compare_parameters(
    fc_params: Dict[str, float],
    target_params: Dict[str, float],
    tol: float = 1e-5
) -> List[ParamDiffItem]:
    """
    Compares live flight controller parameters with target parameters.
    """
    all_keys = sorted(set(fc_params.keys()).union(target_params.keys()))
    results: List[ParamDiffItem] = []

    for name in all_keys:
        group = name.split('_')[0] if '_' in name else name
        is_prot, reason = is_protected_param(name)

        has_fc = name in fc_params
        has_tgt = name in target_params

        fc_val = fc_params.get(name)
        tgt_val = target_params.get(name)

        if has_fc and has_tgt:
            delta = tgt_val - fc_val
            if abs(delta) <= tol:
                status = ParamStatus.MATCH
                is_checked = False
            else:
                if is_prot:
                    status = ParamStatus.PROTECTED
                    is_checked = False
                else:
                    status = ParamStatus.MODIFIED
                    is_checked = True
        elif has_tgt and not has_fc:
            delta = None
            status = ParamStatus.MISSING_IN_FC
            is_checked = not is_prot
        else:  # has_fc and not has_tgt
            delta = None
            status = ParamStatus.EXTRA_IN_FC
            is_checked = False

        results.append(ParamDiffItem(
            name=name,
            group=group,
            fc_value=fc_val,
            target_value=tgt_val,
            delta=delta,
            status=status,
            is_protected=is_prot,
            protection_reason=reason,
            is_checked=is_checked
        ))

    return results
