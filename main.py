"""
main.py — Main entry point for UAV Log Viewer (Python PySide6 Desktop GUI).

Usage:
    python -u main.py [optional_log_filepath]
"""
import sys
import os

# Enable GPU acceleration flags for QtWebEngine before QApplication starts
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                      "--enable-gpu-rasterization --ignore-gpu-blocklist --enable-zero-copy")

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QApplication
from uavlogviewer.gui.main_window import MainWindow

def main():
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("UAV Log Viewer")
    
    window = MainWindow()
    window.show()

    # Optional CLI file argument(s)
    if len(sys.argv) > 1:
        log_paths = [arg for arg in sys.argv[1:] if not arg.startswith("-") and os.path.exists(arg)]
        if log_paths:
            window.load_log_files(log_paths, is_cli=True)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
