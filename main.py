"""
main.py — Main entry point for UAV Log Viewer (Python PySide6 Desktop GUI).

Usage:
    python -u main.py [optional_log_filepath]
"""
import sys
import os
import pyqtgraph as pg

# Configure pyqtgraph global default theme to pure light
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from uavlogviewer.gui.main_window import MainWindow

def setup_light_palette(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#fafafa"))
    pal.setColor(QPalette.WindowText, QColor("#171717"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#f8fafc"))
    pal.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipText, QColor("#171717"))
    pal.setColor(QPalette.Text, QColor("#171717"))
    pal.setColor(QPalette.Button, QColor("#ffffff"))
    pal.setColor(QPalette.ButtonText, QColor("#171717"))
    pal.setColor(QPalette.BrightText, QColor("#ef4444"))
    pal.setColor(QPalette.Link, QColor("#0d9488"))
    pal.setColor(QPalette.Highlight, QColor("#0d9488"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("UAV Log Viewer")
    setup_light_palette(app)
    
    window = MainWindow()
    window.show()

    # Optional CLI file argument
    if len(sys.argv) > 1:
        log_path = sys.argv[1]
        if os.path.exists(log_path):
            window.load_log_file(log_path)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
