# UAV Log Viewer (Python PySide6 Edition)

![log seeking](preview.gif "UAV Log Viewer")

UAV Log Viewer is a high-performance Python desktop application built with PySide6, Plotly, PyMAVLink, and NumPy for parsing and analyzing MAVLink telemetry (`.tlog`, `.mavlink`) and DataFlash logs (`.bin`, `.log`).

## Features

- **Multi-Format Parsing**: Fast parsing for DataFlash (`.bin`, `.log`), MAVLink (`.tlog`), and DJI flight logs.
- **Interactive Multi-Chart GUI**: Drag-and-drop field selection, synchronized crosshair/time-seeking, and flight mode shading.
- **Expression & Sensor Data Calculation**: Custom expressions and parameter viewing.
- **Plotly & PySide6 Desktop Integration**: Rich HTML/SVG visualization powered by Qt WebEngine.

## Installation & Setup

### Prerequisites
- Python 3.9+

### Setup

```bash
# Create and activate virtual environment (optional)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running the Application

```bash
# Run GUI application
python -u main.py

# Open a specific log file directly
python -u main.py path/to/log_file.tlog
```
