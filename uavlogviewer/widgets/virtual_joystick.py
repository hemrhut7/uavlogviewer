"""
virtual_joystick.py — Interactive 2D Virtual Joystick widget with physical gamepad integration.
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter, QPen, QBrush, QColor

from uavlogviewer.mavlink.joystick_reader import get_joystick_reader


class VirtualJoystick(QWidget):
    valueChanged = Signal(float, float)  # (x, y) normalized to [-1.0, 1.0]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self.base_radius = 65
        self.knob_radius = 18
        self.pressed = False
        self.external_pos = QPointF(0, 0)
        self.knob_pos = QPointF(90, 90)

        self.joystick_reader = None
        self._use_gamepad = False
        self._is_right_stick = False
        self.setStyleSheet("background-color: #ffffff;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Force pure white background
        painter.fillRect(self.rect(), QColor("#ffffff"))

        center = QPointF(self.rect().center())

        # Base crosshair & circle
        painter.setPen(QPen(QColor("#cbd5e1"), 2, Qt.DashLine))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawEllipse(center, self.base_radius, self.base_radius)

        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        painter.drawLine(int(center.x() - self.base_radius), int(center.y()), int(center.x() + self.base_radius), int(center.y()))
        painter.drawLine(int(center.x()), int(center.y() - self.base_radius), int(center.x()), int(center.y() + self.base_radius))

        # Knob
        if not self.pressed:
            self.knob_pos = QPointF(center.x() + self.external_pos.x() * self.base_radius,
                                    center.y() - self.external_pos.y() * self.base_radius)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(13, 148, 136, 200)))  # Teal #0d9488
        painter.drawEllipse(self.knob_pos, self.knob_radius, self.knob_radius)

    def mousePressEvent(self, event):
        self.pressed = True
        self._update_knob(event.position())

    def mouseMoveEvent(self, event):
        if self.pressed:
            self._update_knob(event.position())

    def mouseReleaseEvent(self, event):
        self.pressed = False
        self.external_pos = QPointF(0, 0)
        self.update()
        self.valueChanged.emit(0.0, 0.0)

    def _update_knob(self, pos):
        center = QPointF(self.rect().center())
        delta = pos - center
        dist = (delta.x()**2 + delta.y()**2)**0.5

        if dist > self.base_radius:
            delta *= (self.base_radius / dist)

        self.knob_pos = center + delta
        self.update()

        x = delta.x() / self.base_radius
        y = -delta.y() / self.base_radius
        self.valueChanged.emit(x, y)

    def set_joystick_pos(self, x: float, y: float):
        if self.pressed:
            return
        self.external_pos = QPointF(x, y)
        self.update()
        self.valueChanged.emit(x, y)

    def set_use_gamepad(self, enabled: bool, is_right_stick: bool = False):
        self._use_gamepad = enabled
        self._is_right_stick = is_right_stick

        reader = get_joystick_reader()
        if enabled:
            if is_right_stick:
                reader.rightJoystickMoved.connect(self.set_joystick_pos, Qt.UniqueConnection)
            else:
                reader.joystickMoved.connect(self.set_joystick_pos, Qt.UniqueConnection)
            reader.start_reader()
        else:
            try:
                if is_right_stick:
                    reader.rightJoystickMoved.disconnect(self.set_joystick_pos)
                else:
                    reader.joystickMoved.disconnect(self.set_joystick_pos)
            except (TypeError, RuntimeError):
                pass
            reader.stop_reader()
