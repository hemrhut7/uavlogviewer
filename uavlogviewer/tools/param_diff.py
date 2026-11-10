"""
param_diff.py — Comparison tool for vehicle parameters across multiple logs.
"""
from typing import Dict, Any, List, Tuple, Optional
import math


def _values_differ(val1: Optional[Any], val2: Optional[Any], tol: float) -> bool:
    if val1 is None and val2 is None:
        return False
    if val1 is None or val2 is None:
        return True

    # Try numeric comparison
    try:
        f1 = float(val1)
        f2 = float(val2)
        if math.isnan(f1) and math.isnan(f2):
            return False
        return abs(f1 - f2) > tol
    except (ValueError, TypeError):
        return str(val1).strip() != str(val2).strip()


def compute_param_diff(
    params_by_label: Dict[str, Dict[str, Any]],
    only_diff: bool = True,
    tol: float = 1e-6
) -> List[Tuple[str, List[Optional[Any]]]]:
    """
    Compares vehicle parameters across multiple log files.

    Parameters:
        params_by_label: Dict mapping label (e.g. "F1", "F2") to param dict {name: val}.
        only_diff: If True, only returns parameters that differ across logs.
        tol: Tolerance for floating-point parameter comparison.

    Returns:
        List of tuples: (param_name, [val_log1, val_log2, ...]) sorted by param_name.
    """
    labels = list(params_by_label.keys())
    if not labels:
        return []

    # Gather all unique parameter names
    all_param_names = set()
    for p_dict in params_by_label.values():
        if p_dict:
            all_param_names.update(p_dict.keys())

    results: List[Tuple[str, List[Optional[Any]]]] = []

    for name in sorted(all_param_names):
        vals = [params_by_label[lbl].get(name) if params_by_label[lbl] else None for lbl in labels]

        is_different = False
        first_val = vals[0]
        for v in vals[1:]:
            if _values_differ(first_val, v, tol):
                is_different = True
                break

        if not only_diff or is_different:
            results.append((name, vals))

    return results
