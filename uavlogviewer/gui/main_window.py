"""
main_window.py — Main Window container for UAV Log Viewer desktop GUI
with beautified scrollbars and animated file loading progress dialog.

Dependencies: PySide6, sidebar, plot_container, parsers, widgets, chart_store.
"""
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter,
                               QStatusBar, QMessageBox, QProgressDialog)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from typing import Optional, List

from uavlogviewer.gui.sidebar import SidebarWidget
from uavlogviewer.gui.plot_container import PlotContainer
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.models.log_session import LogSession, LoadedLog, MAX_LOGS
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.parsers.dataflash_parser import DataflashParser
from uavlogviewer.parsers.mavlink_parser import MavlinkParser
from uavlogviewer.parsers.csv_parser import CsvParser
from uavlogviewer.widgets.param_viewer import ParamViewerDialog
from uavlogviewer.widgets.message_viewer import MessageViewerDialog
from uavlogviewer.widgets.expression_editor import ExpressionEditorDialog
from uavlogviewer.widgets.coord_transform_dialog import CoordTransformDialog
from uavlogviewer.widgets.export_csv_dialog import ExportCsvDialog
from uavlogviewer.widgets.param_diff_dialog import ParamDiffDialog

MAIN_WINDOW_STYLE = """
QMainWindow { background-color: #fafafa; color: #171717; }
QGroupBox { font-weight: bold; border: 1px solid #e5e5e5; border-radius: 6px; margin-top: 6px; padding-top: 10px; background-color: #ffffff; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; color: #0d9488; }
QPushButton { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
QPushButton:hover { background-color: #f5f5f5; border-color: #0d9488; }
QPushButton:pressed { background-color: #e5e5e5; }
QLineEdit { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 4px 8px; }
QTreeWidget { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; font-size: 12px; }
QStatusBar { background-color: #f5f5f5; color: #525252; }

/* Custom Beautified ScrollBars */
QScrollBar:vertical {
    border: none;
    background: #fafafa;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #0d9488;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    border: none;
    background: #fafafa;
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #cbd5e1;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #0d9488;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
"""

class LogParseWorker(QThread):
    finished = Signal(ParsedLog)
    error = Signal(str)

    def __init__(self, filepath: str, parent=None):
        super().__init__(parent)
        self.filepath = filepath

    def run(self):
        try:
            ext = os.path.splitext(self.filepath)[1].lower()
            if ext in ['.bin', '.log']:
                parser = DataflashParser()
            elif ext == '.tlog':
                parser = MavlinkParser()
            elif ext in ('.csv', '.txt'):
                parser = CsvParser()
            else:
                parser = DataflashParser()

            parsed_log = parser.parse(self.filepath)
            self.finished.emit(parsed_log)
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UAV Log Viewer")
        self.resize(1380, 850)

        # Set Option 3: Vibrant Teal & Coral Palette + Beautified Scrollbar stylesheet
        self.setStyleSheet(MAIN_WINDOW_STYLE)

        self.chart_store = ChartStore()
        self.session = LogSession()
        self.progress_dialog: Optional[QProgressDialog] = None
        self.worker: Optional[LogParseWorker] = None
        self._parse_queue: List[str] = []
        self._current_parsing_file: str = ""
        self._parse_total: int = 0
        self._parse_index: int = 0

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # Left Sidebar Panel
        self.sidebar = SidebarWidget(self.chart_store)
        self.sidebar.set_session(self.session)
        self.sidebar.files_opened.connect(self.load_log_files)
        self.sidebar.log_close_requested.connect(self.close_log)
        self.sidebar.close_all_requested.connect(self.close_all_logs)
        self.sidebar.open_param_diff_requested.connect(self.open_param_diff)
        self.sidebar.open_params_requested.connect(self.open_param_viewer)
        self.sidebar.open_messages_requested.connect(self.open_message_viewer)
        self.sidebar.open_expression_requested.connect(self.open_expression_editor)
        self.sidebar.open_coord_transform_requested.connect(self.open_coord_transform)
        self.sidebar.open_coord_transform_for_chart_requested.connect(self.open_coord_transform_for_chart)
        self.sidebar.open_export_csv_requested.connect(self.open_export_csv_dialog)
        self.splitter.addWidget(self.sidebar)

        # Right Main Plot Container
        self.plot_container = PlotContainer(self.chart_store)
        self.plot_container.set_session(self.session)
        self.plot_container.point_alt_clicked.connect(self.on_chart_alt_clicked)
        self.plot_container.open_export_csv_requested.connect(self.open_export_csv_dialog)
        self.splitter.addWidget(self.plot_container)

        self.splitter.setSizes([380, 1000])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select a log file to begin.")

        self.param_dialog: Optional[ParamViewerDialog] = None
        self.message_dialog: Optional[MessageViewerDialog] = None
        self.expr_dialog: Optional[ExpressionEditorDialog] = None

    @property
    def parsed_log(self) -> Optional[ParsedLog]:
        return self.session.active_log.parsed if self.session.active_log else None

    @parsed_log.setter
    def parsed_log(self, val: Optional[ParsedLog]):
        if val is None:
            self.session.clear()
        else:
            self.session.clear()
            self.session.add_log(val, getattr(val, "filename", "log"))

    def load_log_file(self, filepath: str):
        self.load_log_files([filepath])

    def load_log_files(self, filepaths: List[str], is_cli: bool = False):
        existing = [p for p in filepaths if os.path.exists(p)]
        if not existing:
            if filepaths:
                QMessageBox.critical(self, "File Not Found", f"Cannot find file: {filepaths[0]}")
            return

        # If logs already loaded, not from CLI, and not currently running a queue, ask Append / Replace / Cancel
        is_parsing_active = self.worker is not None and self.worker.isRunning()
        if self.session.logs and not is_cli and not is_parsing_active:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("載入日誌檔案 (Load Log Files)")
            msg_box.setText("目前已有載入的日誌檔案，請問要追加載入或是取代全部？")
            btn_append = msg_box.addButton("追加 (Append)", QMessageBox.AcceptRole)
            btn_replace = msg_box.addButton("取代全部 (Replace All)", QMessageBox.DestructiveRole)
            btn_cancel = msg_box.addButton("取消 (Cancel)", QMessageBox.RejectRole)
            msg_box.setDefaultButton(btn_append)
            msg_box.exec_()

            clicked = msg_box.clickedButton()
            if clicked == btn_cancel:
                return
            elif clicked == btn_replace:
                self.close_all_logs()

        current_paths = {os.path.abspath(l.filepath) for l in self.session.logs}
        queued_paths = {os.path.abspath(p) for p in self._parse_queue}
        if self._current_parsing_file:
            queued_paths.add(os.path.abspath(self._current_parsing_file))

        to_load = []
        for p in existing:
            abs_p = os.path.abspath(p)
            if abs_p in current_paths or abs_p in queued_paths:
                self.status_bar.showMessage(f"檔案已載入或正在佇列中，略過：{os.path.basename(p)}")
                continue
            if len(self.session.logs) + len(to_load) + len(self._parse_queue) >= MAX_LOGS:
                QMessageBox.warning(self, "達到上限", f"最多只能同時載入 {MAX_LOGS} 個日誌檔案。")
                break
            to_load.append(abs_p)

        if not to_load:
            return

        if self.worker is not None and self.worker.isRunning():
            self._parse_queue.extend(to_load)
            self._parse_total += len(to_load)
            return

        self._parse_queue = to_load
        self._parse_total = len(to_load)
        self._parse_index = 0
        self._start_next_parse()

    def _start_next_parse(self):
        # Safely clean up previous worker thread if it exists
        if self.worker is not None:
            if self.worker.isRunning():
                self.worker.wait()
            self.worker.deleteLater()
            self.worker = None

        if not self._parse_queue:
            self._current_parsing_file = ""
            if self.progress_dialog:
                self.progress_dialog.close()
                self.progress_dialog = None
            count = len(self.session.logs)
            self.status_bar.showMessage(f"已成功載入 {count} 個日誌檔案。")
            return

        self._parse_index += 1
        filepath = self._parse_queue.pop(0)
        self._current_parsing_file = filepath
        filename = os.path.basename(filepath)

        msg = f"Parsing log file ({self._parse_index}/{self._parse_total}):\n{filename}..."
        if not self.progress_dialog:
            self.progress_dialog = QProgressDialog(msg, None, 0, 0, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setWindowTitle("Loading Log Files")
            self.progress_dialog.setStyleSheet("""
                QProgressDialog { background-color: #ffffff; color: #171717; font-weight: bold; }
                QProgressBar { border: 1px solid #cbd5e1; border-radius: 4px; text-align: center; background: #fafafa; }
                QProgressBar::chunk { background-color: #0d9488; }
            """)
            self.progress_dialog.show()
        else:
            self.progress_dialog.setLabelText(msg)

        self.worker = LogParseWorker(filepath, self)
        self.worker.finished.connect(self.on_log_parsed)
        self.worker.error.connect(self.on_log_parse_error)
        self.worker.start()

    @Slot(ParsedLog)
    def on_log_parsed(self, parsed_log: ParsedLog):
        loaded = self.session.add_log(parsed_log, self._current_parsing_file)
        self.sidebar.populate_field_tree(parsed_log)
        self.plot_container.update_plots()
        self.status_bar.showMessage(
            f"Loaded [{loaded.label if loaded else '?'}] {parsed_log.filename} successfully."
        )
        QTimer.singleShot(0, self._start_next_parse)

    @Slot(str)
    def on_log_parse_error(self, err_msg: str):
        self.status_bar.showMessage(f"Error parsing log file: {err_msg}")
        QMessageBox.critical(self, "Parse Error", f"Failed to parse log file:\n{err_msg}")
        QTimer.singleShot(0, self._start_next_parse)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(2000)
        event.accept()

    def close_log(self, log_id: int):
        self.chart_store.remove_log(log_id)
        self.session.remove_log(log_id)
        if not self.session.logs:
            self.plot_container.clear_plots()
            self.status_bar.showMessage("已關閉所有日誌檔案。")
        else:
            self.plot_container.update_plots()
            self.status_bar.showMessage(f"已關閉檔案，目前剩餘 {len(self.session.logs)} 個檔案。")

    def close_all_logs(self):
        for l in list(self.session.logs):
            self.chart_store.remove_log(l.log_id)
        self.session.clear()
        self.plot_container.clear_plots()
        self.status_bar.showMessage("已清除所有日誌檔案。")

    def open_param_diff(self):
        if len(self.session.logs) < 2:
            QMessageBox.information(
                self,
                "參數差異比對 (Parameter Difference)",
                "需要至少載入 2 個日誌檔案才能進行參數差異比對。\n請在 Home 頁載入更多檔案。"
            )
            return
        dialog = ParamDiffDialog(self.session, self)
        dialog.exec_()

    def open_param_viewer(self):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        lbl = f"[{self.session.active_log.label}] {self.session.active_log.parsed.filename}" if self.session.active_log else ""
        if not self.param_dialog:
            self.param_dialog = ParamViewerDialog(self.parsed_log.params, self)
        else:
            self.param_dialog.update_params(self.parsed_log.params)
        if lbl:
            self.param_dialog.setWindowTitle(f"Vehicle Parameters — {lbl}")
        self.param_dialog.show()
        self.param_dialog.raise_()

    def open_message_viewer(self):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        lbl = f"[{self.session.active_log.label}] {self.session.active_log.parsed.filename}" if self.session.active_log else ""
        if not self.message_dialog:
            self.message_dialog = MessageViewerDialog(self.parsed_log.text_messages, self)
        else:
            self.message_dialog.update_messages(self.parsed_log.text_messages)
        if lbl:
            self.message_dialog.setWindowTitle(f"Text Messages — {lbl}")
        self.message_dialog.show()
        self.message_dialog.raise_()

    def open_expression_editor(self):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        lbl = f"[{self.session.active_log.label}] {self.session.active_log.parsed.filename}" if self.session.active_log else ""
        self.expr_dialog = ExpressionEditorDialog(self.parsed_log, self)
        self.expr_dialog.expression_added.connect(self.on_expression_added)
        if lbl:
            self.expr_dialog.setWindowTitle(f"Expression Editor — {lbl}")
        self.expr_dialog.show()
        self.expr_dialog.raise_()

    @Slot(str, str)
    def on_expression_added(self, expr_name: str, result_key: str):
        if self.parsed_log:
            self.sidebar.populate_field_tree(self.parsed_log)
            self.chart_store.add_expression(0, result_key, log_id=self.session.active_log_id)
            self.status_bar.showMessage(f"Calculated expression field '{result_key}' added to plot.")

    def on_chart_alt_clicked(self, timestamp: float):
        if not self.parsed_log or not self.session.active_log:
            return
        raw_t = timestamp - self.session.time_shift(self.session.active_log_id)
        self.open_message_viewer()
        if self.message_dialog:
            self.message_dialog.scroll_to_timestamp(raw_t)

    def open_coord_transform(self):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        dialog = CoordTransformDialog(
            self.parsed_log,
            self.chart_store,
            target_chart_idx=None,
            parent=self,
            log_id=self.session.active_log_id
        )
        dialog.calculation_completed.connect(self.on_coord_transform_completed)
        dialog.exec_()

    def open_coord_transform_for_chart(self, chart_idx: int):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        dialog = CoordTransformDialog(
            self.parsed_log,
            self.chart_store,
            target_chart_idx=chart_idx,
            parent=self,
            log_id=self.session.active_log_id
        )
        dialog.calculation_completed.connect(self.on_coord_transform_completed)
        dialog.exec_()

    @Slot(str, str, str)
    def on_coord_transform_completed(self, res_e: str, res_n: str, res_u: str):
        if self.parsed_log:
            self.sidebar.populate_field_tree(self.parsed_log)
        self.plot_container.update_plots()
        self.status_bar.showMessage(f"Coordinates transformed to ENU: {res_e}, {res_n}, {res_u}")

    def open_export_csv_dialog(self):
        if not self.session.logs:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        if not self.chart_store.has_any_expressions():
            QMessageBox.information(
                self,
                "No Plotted Messages",
                "繪圖區目前沒有繪製任何訊息或欄位。\n請先在左側欄雙擊欄位加入繪圖區。"
            )
            return

        dialog = ExportCsvDialog(
            parsed_log=self.parsed_log,
            session=self.session,
            chart_store=self.chart_store,
            visible_range=self.plot_container.current_visible_range,
            parent=self
        )
        dialog.export_completed.connect(self.on_csv_exported)
        dialog.exec_()

    @Slot(str, int)
    def on_csv_exported(self, filepath: str, row_count: int):
        self.status_bar.showMessage(
            f"繪圖區訊息已成功匯出至 CSV: {os.path.basename(filepath)} ({row_count} 列)"
        )
