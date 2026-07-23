"""
main.py — Main entry point for UAV Log Viewer (Python PySide6 Desktop GUI).

Usage:
    python -u main.py [optional_log_filepath]
"""
import sys
import os
from PySide6.QtWidgets import QApplication
from uavlogviewer.gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("UAV Log Viewer")
    
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
