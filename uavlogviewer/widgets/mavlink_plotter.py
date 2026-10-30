"""
mavlink_plotter.py — High-performance real-time telemetry time-series plotter using pyqtgraph.
Supports embedded widget mode, Pop-out standalone window, Combined curves and Stacked subplots.
"""
import time
from typing import Dict, List, Set, Tuple
import numpy as np
import pyqtgraph as pg

# Configure pyqtgraph global default theme to pure light
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from uavlogviewer.mavlink.data_buffer import MavlinkDataBuffer, format_field_label

PLOT_COLORS = [
    "#0d9488",  # Teal
    "#ea580c",  # Coral
    "#0284c7",  # Sky Blue
    "#d97706",  # Amber
    "#7c3aed",  # Violet
    "#e11d48",  # Rose
    "#059669",  # Emerald
    "#4f46e5",  # Indigo
    "#ca8a04",  # Yellow-Gold
    "#db2777",  # Pink
]


class MavlinkPlotWidget(QWidget):
    field_removed = Signal(tuple)
    duration_changed = Signal(int)

    def __init__(self, data_buffer: MavlinkDataBuffer, parent=None):
        super().__init__(parent)
        self.buffer = data_buffer
        self.is_paused = False
        self.popout_dialog: Optional[QDialog] = None

        self.color_map: Dict[Tuple, str] = {}
        self.combined_curves: Dict[Tuple, pg.PlotCurveItem] = {}
        self.subplot_items: Dict[Tuple, dict] = {}

        self.setup_ui()

        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self.update_plots)
        self.plot_timer.start(40)  # 25 Hz

        self.update_fields(self.buffer.get_active_fields())

    def setup_ui(self):
        self.setStyleSheet("""
            MavlinkPlotWidget {
                background-color: #ffffff;
            }
            QLabel {
                background: transparent;
                color: #475569;
            }
            QComboBox {
                background-color: #ffffff;
                color: #171717;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #171717;
                selection-background-color: #f0fdfa;
                selection-color: #0d9488;
            }
            QSpinBox {
                background-color: #ffffff;
                color: #171717;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton {
                background-color: #ffffff;
                color: #171717;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f8fafc;
                border-color: #0d9488;
            }
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        lbl_layout = QLabel("Layout:")
        lbl_layout.setStyleSheet("font-weight: bold; color: #475569;")
        toolbar.addWidget(lbl_layout)

        self.combo_layout_mode = QComboBox()
        self.combo_layout_mode.addItems(["Combined (Single Plot)", "Subplots (Stacked)"])
        self.combo_layout_mode.currentIndexChanged.connect(self.on_layout_mode_changed)
        toolbar.addWidget(self.combo_layout_mode)

        toolbar.addSpacing(6)

        lbl_dur = QLabel("Window:")
        lbl_dur.setStyleSheet("font-weight: bold; color: #475569;")
        toolbar.addWidget(lbl_dur)

        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(5, 3600)
        self.spin_duration.setValue(int(self.buffer.get_duration()))
        self.spin_duration.setSuffix(" s")
        self.spin_duration.valueChanged.connect(self.on_duration_changed)
        toolbar.addWidget(self.spin_duration)

        toolbar.addSpacing(6)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self.toggle_pause)
        toolbar.addWidget(self.btn_pause)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_data)
        toolbar.addWidget(self.btn_clear)

        toolbar.addStretch()

        self.btn_popout = QPushButton("Pop-Out Window")
        self.btn_popout.setStyleSheet("background-color: #0d9488; color: white; border: none; font-weight: bold;")
        self.btn_popout.clicked.connect(self.toggle_popout)
        toolbar.addWidget(self.btn_popout)

        main_layout.addLayout(toolbar)

        # Chips / Badges Area for active fields
        self.chips_layout = QHBoxLayout()
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(6)
        self.chips_container = QWidget()
        self.chips_container.setLayout(self.chips_layout)

        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFixedHeight(32)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        chips_scroll.setWidget(self.chips_container)
        chips_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        main_layout.addWidget(chips_scroll)

        # Stacked Views: 0 = Combined, 1 = Subplots
        self.stack = QStackedWidget()

        # Combined Plot
        self.combined_plot = pg.PlotWidget()
        self.configure_plot_widget(self.combined_plot)
        self.combined_plot.setLabel('bottom', "Time relative to now", units='s')
        self.combined_legend = self.combined_plot.addLegend(offset=(10, 10))
        self.combined_legend.setBrush(pg.mkBrush(255, 255, 255, 210))
        self.combined_legend.setPen(pg.mkPen("#cbd5e1"))
        self.stack.addWidget(self.combined_plot)

        # Subplots Scroll
        self.subplots_scroll = QScrollArea()
        self.subplots_scroll.setWidgetResizable(True)
        self.subplots_scroll.setStyleSheet("QScrollArea { background-color: #ffffff; border: none; }")
        self.subplots_container = QWidget()
        self.subplots_container.setStyleSheet("background-color: #ffffff;")
        self.subplots_layout = QVBoxLayout(self.subplots_container)
        self.subplots_layout.setContentsMargins(0, 0, 0, 0)
        self.subplots_layout.setSpacing(6)
        self.subplots_scroll.setWidget(self.subplots_container)
        self.stack.addWidget(self.subplots_scroll)

        main_layout.addWidget(self.stack, 1)

    def configure_plot_widget(self, plot: pg.PlotWidget):
        plot.setBackground("#ffffff")
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.getAxis('left').setPen(pg.mkPen('#94a3b8'))
        plot.getAxis('bottom').setPen(pg.mkPen('#94a3b8'))
        plot.getAxis('left').setTextPen(pg.mkPen('#475569'))
        plot.getAxis('bottom').setTextPen(pg.mkPen('#475569'))

    def update_fields(self, selected_fields: Set[Tuple]):
        current_keys = set(self.color_map.keys())
        target_keys = set(selected_fields)

        # Removed keys
        for key in current_keys - target_keys:
            del self.color_map[key]
            if key in self.combined_curves:
                self.combined_plot.removeItem(self.combined_curves[key])
                self.combined_legend.removeItem(self.combined_curves[key])
                del self.combined_curves[key]
            if key in self.subplot_items:
                pw = self.subplot_items[key]['plot_widget']
                self.subplots_layout.removeWidget(pw)
                pw.deleteLater()
                del self.subplot_items[key]

        # Added keys
        for key in target_keys - current_keys:
            used_colors = set(self.color_map.values())
            avail_colors = [c for c in PLOT_COLORS if c not in used_colors]
            color = avail_colors[0] if avail_colors else PLOT_COLORS[len(self.color_map) % len(PLOT_COLORS)]
            self.color_map[key] = color

            # Add to combined plot
            lbl = format_field_label(key)
            curve = self.combined_plot.plot(pen=pg.mkPen(color=color, width=2.0), name=lbl)
            self.combined_curves[key] = curve

            # Add to subplots
            pw = pg.PlotWidget()
            self.configure_plot_widget(pw)
            pw.setFixedHeight(140)
            pw.setLabel('left', f"{key[2]}.{key[3]}")
            sub_curve = pw.plot(pen=pg.mkPen(color=color, width=2.0))
            self.subplot_items[key] = {'plot_widget': pw, 'curve': sub_curve}
            self.subplots_layout.addWidget(pw)

        self.rebuild_chips(selected_fields)

    def rebuild_chips(self, fields: Set[Tuple]):
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for key in sorted(fields, key=lambda k: (k[0], k[2], k[3])):
            color = self.color_map.get(key, "#0d9488")
            lbl_text = format_field_label(key)

            chip = QFrame()
            chip.setStyleSheet(f"""
                QFrame {{
                    background-color: #f1f5f9;
                    border: 1px solid {color};
                    border-radius: 4px;
                }}
            """)
            c_lay = QHBoxLayout(chip)
            c_lay.setContentsMargins(6, 2, 4, 2)
            c_lay.setSpacing(4)

            color_box = QFrame()
            color_box.setFixedSize(8, 8)
            color_box.setStyleSheet(f"background-color: {color}; border-radius: 4px; border: none;")
            c_lay.addWidget(color_box)

            t_lbl = QLabel(lbl_text)
            t_lbl.setStyleSheet("color: #171717; font-size: 11px; font-weight: bold; border: none;")
            c_lay.addWidget(t_lbl)

            btn_del = QPushButton("x")
            btn_del.setFixedSize(14, 14)
            btn_del.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #94a3b8;
                    border: none;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover { color: #ef4444; }
            """)
            btn_del.clicked.connect(lambda checked=False, k=key: self.field_removed.emit(k))
            c_lay.addWidget(btn_del)

            self.chips_layout.addWidget(chip)

        self.chips_layout.addStretch()

    def update_plots(self):
        if self.is_paused or not self.color_map:
            return

        now = time.time()
        duration = self.buffer.get_duration()
        is_subplots = (self.stack.currentIndex() == 1)

        for key in self.color_map.keys():
            ts, vs = self.buffer.get_field_data(key)
            if len(ts) == 0:
                continue

            rel_time = ts - now
            if not is_subplots:
                if key in self.combined_curves:
                    self.combined_curves[key].setData(rel_time, vs)
            else:
                if key in self.subplot_items:
                    self.subplot_items[key]['curve'].setData(rel_time, vs)
                    self.subplot_items[key]['plot_widget'].setXRange(-duration, 0, padding=0.02)

        if not is_subplots:
            self.combined_plot.setXRange(-duration, 0, padding=0.02)

    def on_layout_mode_changed(self, idx: int):
        self.stack.setCurrentIndex(idx)

    def on_duration_changed(self, val: int):
        self.buffer.set_duration(val)
        self.duration_changed.emit(val)

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.btn_pause.setText("Resume" if self.is_paused else "Pause")

    def clear_data(self):
        self.buffer.clear_data()
        for curve in self.combined_curves.values():
            curve.clear()
        for item in self.subplot_items.values():
            item['curve'].clear()

    def toggle_popout(self):
        if self.popout_dialog and self.popout_dialog.isVisible():
            self.popout_dialog.raise_()
            self.popout_dialog.activateWindow()
            return

        self.popout_dialog = QDialog(self)
        self.popout_dialog.setWindowTitle("MAVLink Real-Time Telemetry Plotter (Pop-Out)")
        self.popout_dialog.setStyleSheet("QDialog { background-color: #fafafa; color: #171717; }")
        self.popout_dialog.resize(950, 600)
        d_lay = QVBoxLayout(self.popout_dialog)
        d_lay.setContentsMargins(8, 8, 8, 8)

        # Move stack to dialog or create popout widget
        d_lbl = QLabel("Independent floating monitor window. Close this window to return.")
        d_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        d_lay.addWidget(d_lbl)

        # Duplicate plot widget in dialog
        popout_content = MavlinkPlotWidget(self.buffer, parent=self.popout_dialog)
        popout_content.btn_popout.setVisible(False)
        d_lay.addWidget(popout_content)

        self.popout_dialog.show()
