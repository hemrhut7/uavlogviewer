"""
chart_store.py — Central state management for multi-chart, dual-axis (Axis 1 & Axis 2),
and inline calculation builder configurations.

Dependencies: PySide6.
"""
from PySide6.QtCore import QObject, Signal
from typing import List, Dict, Any, Optional

DEFAULT_AXIS_COLORS = [
    '#0d9488', '#ea580c', '#2563eb', '#db2777', '#7c3aed', '#16a34a',
    '#ca8a04', '#0891b2', '#e11d48', '#059669', '#d97706', '#9333ea'
]

class CalcBuilderState:
    def __init__(self):
        self.active_operand: str = 'A'  # 'A' or 'B'
        self.operand_a: str = ''
        self.operator: str = '*'        # '+', '-', '*', '/'
        self.operand_b: str = ''

class ChartItem:
    def __init__(self, name: str, axis: int = 0, color: str = None):
        self.name = name
        self.axis = min(max(0, axis), 1)
        self.color = color or DEFAULT_AXIS_COLORS[axis % len(DEFAULT_AXIS_COLORS)]

class ChartPanel:
    def __init__(self, name: str = "Chart"):
        self.name = name
        self.expressions: List[ChartItem] = []
        self.pending_builder: Optional[CalcBuilderState] = None

class ChartStore(QObject):
    updated = Signal()

    def __init__(self):
        super().__init__()
        self.sync_zoom: bool = True
        self.stats_full_range: bool = True
        self.charts: List[ChartPanel] = [ChartPanel("Chart 1")]

    def add_chart(self) -> int:
        idx = len(self.charts) + 1
        self.charts.append(ChartPanel(f"Chart {idx}"))
        self.updated.emit()
        return len(self.charts) - 1

    def remove_chart(self, chart_idx: int):
        if 0 <= chart_idx < len(self.charts) and len(self.charts) > 1:
            self.charts.pop(chart_idx)
            self.updated.emit()

    def clear_chart(self, chart_idx: int):
        if 0 <= chart_idx < len(self.charts):
            self.charts[chart_idx].expressions.clear()
            self.charts[chart_idx].pending_builder = None
            self.updated.emit()

    def add_expression(self, chart_idx: int, expr_name: str, axis: int = 0, color: str = None):
        if 0 <= chart_idx < len(self.charts):
            chart = self.charts[chart_idx]
            for item in chart.expressions:
                if item.name == expr_name:
                    return
            
            clean_axis = min(max(0, axis), 1)
            if color is None:
                color = DEFAULT_AXIS_COLORS[len(chart.expressions) % len(DEFAULT_AXIS_COLORS)]

            chart.expressions.append(ChartItem(name=expr_name, axis=clean_axis, color=color))
            self.updated.emit()

    def remove_expression(self, chart_idx: int, expr_name: str):
        if 0 <= chart_idx < len(self.charts):
            chart = self.charts[chart_idx]
            chart.expressions = [e for e in chart.expressions if e.name != expr_name]
            self.updated.emit()

    def set_expression_axis(self, chart_idx: int, expr_name: str, axis: int):
        if 0 <= chart_idx < len(self.charts):
            clean_axis = min(max(0, axis), 1)
            for e in self.charts[chart_idx].expressions:
                if e.name == expr_name:
                    e.axis = clean_axis
                    break
            self.updated.emit()

    def set_expression_color(self, chart_idx: int, expr_name: str, color: str):
        if 0 <= chart_idx < len(self.charts):
            for e in self.charts[chart_idx].expressions:
                if e.name == expr_name:
                    e.color = color
                    break
            self.updated.emit()

    def has_any_expressions(self) -> bool:
        return any(len(c.expressions) > 0 for c in self.charts)
