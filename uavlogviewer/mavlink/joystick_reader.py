"""
joystick_reader.py — Physical Gamepad / Joystick reader using pygame.
"""
import os
from typing import Optional
from PySide6.QtCore import QObject, QTimer, Signal

_joystick_reader_instance = None


def get_joystick_reader():
    global _joystick_reader_instance
    if _joystick_reader_instance is None:
        _joystick_reader_instance = JoystickReader()
    return _joystick_reader_instance


class JoystickReader(QObject):
    joystickMoved = Signal(float, float)        # Left Stick (x, y in [-1, 1])
    rightJoystickMoved = Signal(float, float)   # Right Stick (x, y in [-1, 1])
    connectionStatus = Signal(bool, str)        # (is_connected, device_name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.joystick = None
        self.deadzone = 0.08
        self._ref_count = 0
        self.last_axes = [0.0] * 6

        # Disable pygame welcome message
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
        os.environ['SDL_VIDEODRIVER'] = "dummy"

        try:
            import pygame
            self.pygame = pygame
            if not self.pygame.get_init():
                self.pygame.init()
            if not self.pygame.joystick.get_init():
                self.pygame.joystick.init()
        except ImportError:
            self.pygame = None

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)

    def start_reader(self):
        if not self.pygame:
            return
        self._ref_count += 1
        if not self.poll_timer.isActive():
            try:
                if self.pygame.joystick.get_init():
                    self.pygame.joystick.quit()
                self.pygame.joystick.init()
            except Exception as e:
                print(f"Joystick re-init error: {e}")

            self.poll_timer.start(25)  # 40 Hz polling

    def stop_reader(self):
        self._ref_count -= 1
        if self._ref_count <= 0:
            self._ref_count = 0
            self.poll_timer.stop()

    def shutdown(self):
        self.poll_timer.stop()
        if self.joystick:
            try:
                self.joystick.quit()
            except Exception:
                pass
            self.joystick = None

    def _poll(self):
        if not self.pygame:
            return

        for event in self.pygame.event.get():
            pass

        count = self.pygame.joystick.get_count()
        if count == 0:
            if self.joystick is not None:
                try:
                    self.joystick.quit()
                except Exception:
                    pass
                self.joystick = None
                self.connectionStatus.emit(False, "None")
            return

        if self.joystick is None:
            try:
                self.joystick = self.pygame.joystick.Joystick(0)
                self.joystick.init()
                name = self.joystick.get_name()
                self.connectionStatus.emit(True, name)
            except Exception:
                return

        try:
            num_axes = self.joystick.get_numaxes()
            lx = self.joystick.get_axis(0) if num_axes > 0 else 0.0
            ly = -self.joystick.get_axis(1) if num_axes > 1 else 0.0
            rx = self.joystick.get_axis(3) if num_axes > 3 else 0.0
            ry = -self.joystick.get_axis(4) if num_axes > 4 else 0.0

            if abs(lx) < self.deadzone: lx = 0.0
            if abs(ly) < self.deadzone: ly = 0.0
            if abs(rx) < self.deadzone: rx = 0.0
            if abs(ry) < self.deadzone: ry = 0.0

            if abs(lx - self.last_axes[0]) > 0.01 or abs(ly - self.last_axes[1]) > 0.01:
                self.joystickMoved.emit(lx, ly)
                self.last_axes[0], self.last_axes[1] = lx, ly

            if abs(rx - self.last_axes[3]) > 0.01 or abs(ry - self.last_axes[4]) > 0.01:
                self.rightJoystickMoved.emit(rx, ry)
                self.last_axes[3], self.last_axes[4] = rx, ry

        except Exception as e:
            self.joystick = None
