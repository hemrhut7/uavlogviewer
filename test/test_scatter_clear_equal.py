"""Tests for Scatter Clear All and 1:1 equal-aspect lock."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import numpy as np
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.tools.plotly_exporter import generate_plotly_html


def _log():
    log = ParsedLog(filename="f.bin", log_type="dataflash")
    t = np.linspace(0.0, 10.0, 50)
    log.timestamps["A"] = t
    log.time_series["A.x"] = np.sin(t) * 100
    log.time_series["A.y"] = np.cos(t)
    log.field_tree = {"A": ["x", "y"]}
    return log


def _scatter_store():
    store = ChartStore()
    store.add_xy_chart() if hasattr(store, "add_xy_chart") else None
    idx = next(i for i, c in enumerate(store.charts) if c.chart_type == "scatter")
    return store, idx


def test_clear_scatter_pairs():
    store, idx = _scatter_store()
    chart = store.charts[idx]
    chart.pairs[0].x_field, chart.pairs[0].y_field = "A.x", "A.y"
    store.clear_chart(idx)
    assert len(chart.pairs) == 1 and not chart.pairs[0].x_field and not chart.pairs[0].y_field


def test_equal_aspect_toggle_and_html():
    store, idx = _scatter_store()
    chart = store.charts[idx]
    chart.pairs[0].x_field, chart.pairs[0].y_field = "A.x", "A.y"
    log = _log()
    assert "\"scaleanchor\":\"x" not in generate_plotly_html(log, store)
    store.toggle_equal_aspect_all_scatter()
    assert chart.equal_aspect
    html = generate_plotly_html(log, store)
    assert '"scaleanchor":"x' in html and "modeBarButtonsToAdd" in html
    store.toggle_equal_aspect_all_scatter()
    assert not chart.equal_aspect
