"""
plot_container.py — Pure Plotly Embedded Viewport (QWebEngineView) styled with Option 3: Vibrant Teal & Coral Theme,
dynamic visible time range statistics calculation with structured QTableWidget panel (Min, Max, Mean, STD, Last Value)
and soft light green / white alternating row backgrounds.

Dependencies: PySide6, numpy, chart_store, plotly_exporter, QtWebEngineWidgets.
"""
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QHeaderView, QGroupBox, QFileDialog)
from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
import numpy as np
from typing import Optional, List
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.tools.plotly_exporter import generate_plotly_html, filter_by_segment, get_series_data_and_timestamps

class PlotContainer(QWidget):
    point_alt_clicked = Signal(float)

    def __init__(self, chart_store: ChartStore, parent=None):
        super().__init__(parent)
        self.chart_store = chart_store
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Plotly Embedded Viewport Widget (QWebEngineView)
        self.plotly_web_view = QWebEngineView()
        self.plotly_web_view.page().profile().downloadRequested.connect(self.on_download_requested)
        self.plotly_web_view.titleChanged.connect(self.on_web_title_changed)
        self.layout.addWidget(self.plotly_web_view, stretch=4)

        # Structured Viewport Statistics Box & Table Widget
        self.stats_box = QGroupBox("📊 [Full Range]")
        self.stats_box.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 11px; border: 1px solid #e5e5e5; border-radius: 4px; background: #fafafa; margin-top: 4px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; color: #0d9488; }
        """)
        stats_box_layout = QVBoxLayout(self.stats_box)
        stats_box_layout.setContentsMargins(4, 4, 4, 4)

        self.stats_table = QTableWidget(0, 7)
        self.stats_table.setHorizontalHeaderLabels(["Chart", "Telemetry Field", "Min", "Max", "Mean", "STD", "Last Value"])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setAlternatingRowColors(True)

        # Force Light Green & White Alternating Palette
        pal = self.stats_table.palette()
        pal.setColor(QPalette.Base, QColor("#ffffff"))
        pal.setColor(QPalette.AlternateBase, QColor("#f0fdf4"))
        self.stats_table.setPalette(pal)

        self.stats_table.setMaximumHeight(125)
        self.stats_table.setStyleSheet("""
            QTableWidget { background-color: #ffffff; alternate-background-color: #f0fdf4; color: #171717; gridline-color: #e5e5e5; font-size: 11px; border: 1px solid #e5e5e5; }
            QTableWidget::item:alternate { background-color: #f0fdf4; }
            QHeaderView::section { background-color: #0d9488; color: #ffffff; font-weight: bold; font-size: 11px; padding: 3px; border: none; }
            QTableWidget::item { padding: 2px 4px; }
        """)
        stats_box_layout.addWidget(self.stats_table)

        self.layout.addWidget(self.stats_box, stretch=1)

        self.parsed_log: Optional[ParsedLog] = None
        self.current_visible_range: Optional[tuple] = None

        self.chart_store.updated.connect(self.update_plots)

    def set_parsed_log(self, parsed_log: ParsedLog):
        self.parsed_log = parsed_log
        self.current_visible_range = None
        self.update_plots()

    def clear_plots(self):
        self.stats_box.setTitle("📊 [No Log Loaded]")
        self.stats_table.setRowCount(0)
        self.plotly_web_view.setHtml("<html><body style='background-color:#fafafa;'></body></html>")

    def update_plots(self):
        if not self.parsed_log:
            self.clear_plots()
            return

        if not self.chart_store.has_any_expressions():
            self.stats_box.setTitle("📊 [No Fields Plotted]")
            self.stats_table.setRowCount(0)
            self.update_embedded_plotly()
            return

        self.update_stats_for_range(self.current_visible_range[0] if self.current_visible_range else None,
                                   self.current_visible_range[1] if self.current_visible_range else None)
        self.update_embedded_plotly()

    def update_embedded_plotly(self):
        if not self.parsed_log or not self.chart_store:
            return

        html_str = generate_plotly_html(self.parsed_log, self.chart_store, visible_range=self.current_visible_range)
        
        tmp_dir = os.path.abspath(".agent_scratchpad")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_file = os.path.join(tmp_dir, "plotly_preview.html")

        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(html_str)
            self.plotly_web_view.load(QUrl.fromLocalFile(tmp_file))
        except Exception as e:
            print(f"Error updating Plotly viewport: {e}")

    def on_download_requested(self, download_item: QWebEngineDownloadRequest):
        suggested_name = download_item.suggestedFileName() or download_item.downloadFileName() or "newplot.png"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Plot Image",
            suggested_name,
            "PNG Image (*.png);;All Files (*)"
        )
        if file_path:
            download_item.setDownloadDirectory(os.path.dirname(file_path))
            download_item.setDownloadFileName(os.path.basename(file_path))
            download_item.accept()
        else:
            download_item.cancel()

    def on_web_title_changed(self, title: str):
        if not title:
            return

        if title.startswith("CLICK_TIME:"):
            try:
                t_val = float(title.split(":")[1])
                self.point_alt_clicked.emit(t_val)
            except ValueError:
                pass
            return

        if not title.startswith("RANGE:") or not self.parsed_log:
            return

        has_scatter = any(c.chart_type == "scatter" for c in self.chart_store.charts)

        parts = title.split(":")
        if len(parts) == 3 and parts[1] != "RESET":
            try:
                x0, x1 = float(parts[1]), float(parts[2])
                self.current_visible_range = (x0, x1)
                self.update_stats_for_range(x0, x1)
                if has_scatter:
                    self.update_embedded_plotly()
            except ValueError:
                pass
        elif "RESET" in title:
            self.current_visible_range = None
            self.update_stats_for_range(None, None)
            if has_scatter:
                self.update_embedded_plotly()

    def update_stats_for_range(self, x0: Optional[float] = None, x1: Optional[float] = None):
        if not self.parsed_log:
            return

        active_charts = [c for c in self.chart_store.charts if len(c.expressions) > 0]
        if not active_charts:
            self.stats_box.setTitle("📊 [No Fields Plotted]")
            self.stats_table.setRowCount(0)
            return

        range_tag = f" [{x0:.1f}s ~ {x1:.1f}s, dt = {x1 - x0:.1f}s]" if (x0 is not None and x1 is not None) else " [Full Range]"
        self.stats_box.setTitle(f"📊 {range_tag}")

        table_rows = []

        for c_idx, chart in enumerate(active_charts):
            for expr in chart.expressions:
                field_key = expr.name
                t_arr, y_arr = get_series_data_and_timestamps(self.parsed_log, field_key)
                if len(y_arr) == 0:
                    continue
                t_arr, y_arr = filter_by_segment(t_arr, y_arr, self.parsed_log, self.chart_store.segment_filter)

                if x0 is not None and x1 is not None and len(t_arr) > 0:
                    mask = (t_arr >= x0) & (t_arr <= x1)
                    if np.any(mask):
                        y_sub = y_arr[mask]
                        ymin, ymax = float(np.nanmin(y_sub)), float(np.nanmax(y_sub))
                        ymean = float(np.nanmean(y_sub))
                        ystd = float(np.nanstd(y_sub))
                        ylast = float(y_sub[-1])
                    else:
                        continue
                else:
                    ymin, ymax = float(np.nanmin(y_arr)), float(np.nanmax(y_arr))
                    ymean = float(np.nanmean(y_arr))
                    ystd = float(np.nanstd(y_arr))
                    ylast = float(y_arr[-1]) if len(y_arr) > 0 else 0.0

                table_rows.append((
                    f"Chart #{c_idx + 1}",
                    field_key,
                    f"{ymin:.4f}",
                    f"{ymax:.4f}",
                    f"{ymean:.4f}",
                    f"{ystd:.4f}",
                    f"{ylast:.4f}"
                ))

        self.stats_table.setRowCount(len(table_rows))
        for row_idx, row_data in enumerate(table_rows):
            for col_idx, text in enumerate(row_data):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                self.stats_table.setItem(row_idx, col_idx, item)
