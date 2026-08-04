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
        self.active_operand: str = 'A'  # 'A', 'B', etc.
        self.operand_a: str = ''
        self.operator: str = '+'        # '+', '-', '*', '/', 'norm', 'wrap_180', 'wrap_360', 'rad2deg', 'deg2rad', 'ang_sub'
        self.operand_b: str = ''
        self.norm_operands: List[str] = []
        self.active_norm_idx: int = 0

class ChartItem:
    def __init__(self, name: str, axis: int = 0, color: str = None):
        self.name = name
        self.axis = min(max(0, axis), 1)
        self.color = color or DEFAULT_AXIS_COLORS[axis % len(DEFAULT_AXIS_COLORS)]

class XYScatterPair:
    def __init__(self, x_field: str = "", y_field: str = "", color: str = None):
        self.x_field = x_field
        self.y_field = y_field
        self.color = color or DEFAULT_AXIS_COLORS[0]

class ChartPanel:
    def __init__(self, name: str = "Chart", chart_type: str = "timeseries"):
        self.name = name
        self.chart_type = chart_type  # "timeseries" or "scatter"
        self.expressions: List[ChartItem] = []
        self.pending_builder: Optional[CalcBuilderState] = None
        # Multiple XY Scatter pairs
        self.pairs: List[XYScatterPair] = []
        self.active_pair_idx: int = 0
        self.active_xy_target: str = 'X'  # 'X' or 'Y'
        self.max_points: int = 5000  # Default max rendering points limit for scatter

    @property
    def x_field(self) -> str:
        if self.pairs and 0 <= self.active_pair_idx < len(self.pairs):
            return self.pairs[self.active_pair_idx].x_field
        return ""

    @x_field.setter
    def x_field(self, val: str):
        if self.pairs and 0 <= self.active_pair_idx < len(self.pairs):
            self.pairs[self.active_pair_idx].x_field = val

    @property
    def y_field(self) -> str:
        if self.pairs and 0 <= self.active_pair_idx < len(self.pairs):
            return self.pairs[self.active_pair_idx].y_field
        return ""

    @y_field.setter
    def y_field(self, val: str):
        if self.pairs and 0 <= self.active_pair_idx < len(self.pairs):
            self.pairs[self.active_pair_idx].y_field = val

class ChartStore(QObject):
    updated = Signal()

    def __init__(self):
        super().__init__()
        self.sync_zoom: bool = False
        self.stats_full_range: bool = True
        self.segment_filter: str = "longest"  # "longest" (default), "all", or "0", "1", "2"
        self.charts: List[ChartPanel] = [ChartPanel("Chart 1")]

    def set_segment_filter(self, mode: str):
        if self.segment_filter != mode:
            self.segment_filter = mode
            self.updated.emit()

    def add_chart(self) -> int:
        idx = len(self.charts) + 1
        self.charts.append(ChartPanel(f"Chart {idx}"))
        self.updated.emit()
        return len(self.charts) - 1

    def add_xy_chart(self, x_field: str = "", y_field: str = "") -> int:
        idx = len(self.charts) + 1
        panel = ChartPanel(f"XY Scatter {idx}", chart_type="scatter")
        color = DEFAULT_AXIS_COLORS[0]
        panel.pairs = [XYScatterPair(x_field, y_field, color=color)]
        panel.active_pair_idx = 0
        panel.active_xy_target = 'X'
        self.charts.append(panel)
        self.updated.emit()
        return len(self.charts) - 1

    def add_xy_pair(self, chart_idx: int, x_field: str = "", y_field: str = ""):
        if 0 <= chart_idx < len(self.charts):
            chart = self.charts[chart_idx]
            if chart.chart_type == "scatter":
                color = DEFAULT_AXIS_COLORS[len(chart.pairs) % len(DEFAULT_AXIS_COLORS)]
                chart.pairs.append(XYScatterPair(x_field, y_field, color=color))
                chart.active_pair_idx = len(chart.pairs) - 1
                chart.active_xy_target = 'X'
                self.updated.emit()

    def remove_xy_pair(self, chart_idx: int, pair_idx: int):
        if 0 <= chart_idx < len(self.charts):
            chart = self.charts[chart_idx]
            if chart.chart_type == "scatter" and 0 <= pair_idx < len(chart.pairs):
                chart.pairs.pop(pair_idx)
                if not chart.pairs:
                    chart.pairs.append(XYScatterPair(color=DEFAULT_AXIS_COLORS[0]))
                chart.active_pair_idx = max(0, min(chart.active_pair_idx, len(chart.pairs) - 1))
                self.updated.emit()

    def get_plotted_fields(self) -> List[str]:
        """Returns a list of unique field names already plotted in standard timeseries charts."""
        fields = []
        for c in self.charts:
            if c.chart_type == "timeseries":
                for expr in c.expressions:
                    if expr.name not in fields:
                        fields.append(expr.name)
            elif c.chart_type == "scatter":
                for p in c.pairs:
                    if p.x_field and p.x_field not in fields:
                        fields.append(p.x_field)
                    if p.y_field and p.y_field not in fields:
                        fields.append(p.y_field)
        return fields

    def remove_chart(self, chart_idx: int):
        if 0 <= chart_idx < len(self.charts) and len(self.charts) > 1:
            self.charts.pop(chart_idx)
            self.updated.emit()

    def clear_chart(self, chart_idx: int):
        if 0 <= chart_idx < len(self.charts):
            chart = self.charts[chart_idx]
            chart.expressions.clear()
            chart.pending_builder = None
            chart.pairs = [XYScatterPair(color=DEFAULT_AXIS_COLORS[0])]
            chart.active_pair_idx = 0
            self.updated.emit()

    def add_expression(self, chart_idx: int, expr_name: str, axis: int = 0, color: str = None):
        if 0 <= chart_idx < len(self.charts):
            chart = self.charts[chart_idx]
            if chart.chart_type == "scatter":
                if chart.pairs and 0 <= chart.active_pair_idx < len(chart.pairs):
                    pair = chart.pairs[chart.active_pair_idx]
                    if chart.active_xy_target == 'X':
                        pair.x_field = expr_name
                        chart.active_xy_target = 'Y'
                    else:
                        pair.y_field = expr_name
                    self.updated.emit()
                return

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

    def set_chart_max_points(self, chart_idx: int, max_pts: int):
        if 0 <= chart_idx < len(self.charts):
            self.charts[chart_idx].max_points = max_pts
            self.updated.emit()

    def set_xy_field(self, chart_idx: int, target: str, field_name: str):
        if 0 <= chart_idx < len(self.charts):
            chart = self.charts[chart_idx]
            if chart.chart_type == "scatter" and chart.pairs:
                pair = chart.pairs[chart.active_pair_idx]
                if target == 'X':
                    pair.x_field = field_name
                elif target == 'Y':
                    pair.y_field = field_name
                self.updated.emit()

    def has_any_expressions(self) -> bool:
        return any(
            (c.chart_type == "timeseries" and len(c.expressions) > 0) or
            (c.chart_type == "scatter" and any(p.x_field != "" or p.y_field != "" for p in c.pairs))
            for c in self.charts
        )
