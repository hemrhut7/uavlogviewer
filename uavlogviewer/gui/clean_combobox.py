"""
clean_combobox.py — Styled QComboBox with clean popup container background.
Eliminates dark/black margins above and below dropdown options under Linux/dark OS themes.
"""
from PySide6.QtWidgets import QComboBox, QListView, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor

class CleanComboBox(QComboBox):
    def __init__(self, parent=None, border_color="#0d9488", hover_bg="#f0fdfa", text_color="#0f766e", font_size="11px", min_width=None, max_width=None, padding="2px 14px 2px 6px"):
        super().__init__(parent)
        self.border_color = border_color
        self.hover_bg = hover_bg
        self.text_color = text_color

        view = QListView(self)
        self.setView(view)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        # Configure palette on view & viewport
        p = view.palette()
        p.setColor(QPalette.Window, QColor("#ffffff"))
        p.setColor(QPalette.Base, QColor("#ffffff"))
        p.setColor(QPalette.AlternateBase, QColor("#ffffff"))
        p.setColor(QPalette.WindowText, QColor(text_color))
        p.setColor(QPalette.Text, QColor(text_color))
        p.setColor(QPalette.Highlight, QColor("#ccfbf1"))
        p.setColor(QPalette.HighlightedText, QColor(text_color))
        view.setPalette(p)
        view.viewport().setPalette(p)

        min_w_str = f"min-width: {min_width};" if min_width else ""
        max_w_str = f"max-width: {max_width};" if max_width else ""

        self.setStyleSheet(f"""
            QComboBox {{
                background-color: #ffffff;
                color: {text_color};
                font-weight: bold;
                font-size: {font_size};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: {padding};
                {min_w_str}
                {max_w_str}
            }}
            QComboBox:hover {{
                background-color: {hover_bg};
                border-color: {text_color};
            }}
            QComboBox:focus {{
                border-color: {border_color};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 14px;
                border: none;
            }}
            QComboBox::down-arrow {{
                width: 0px;
                height: 0px;
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid {border_color};
                margin-right: 3px;
            }}
            QComboBox::down-arrow:hover {{
                border-top: 4px solid {text_color};
            }}
            QComboBox QAbstractItemView {{
                background-color: #ffffff;
                background: #ffffff;
                color: {text_color};
                font-weight: bold;
                font-size: {font_size};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 2px 0px;
                margin: 0px;
                outline: 0px;
                selection-background-color: #ccfbf1;
                selection-color: {text_color};
            }}
            QComboBox QAbstractItemView::viewport {{
                background-color: #ffffff;
                background: #ffffff;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 16px;
                padding: 2px 5px;
                border-radius: 3px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {hover_bg};
                color: {text_color};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: #ccfbf1;
                color: {text_color};
            }}
        """)

    def showPopup(self):
        fm = self.fontMetrics()
        max_w = self.width()
        for i in range(self.count()):
            w = fm.horizontalAdvance(self.itemText(i)) + 36
            if w > max_w:
                max_w = w
        self.view().setMinimumWidth(max_w)

        super().showPopup()
        container = self.view().parentWidget()
        if container:
            container.setContentsMargins(0, 0, 0, 0)
            if container.layout():
                container.layout().setContentsMargins(0, 0, 0, 0)
                container.layout().setSpacing(0)
            if isinstance(container, QFrame):
                container.setFrameShape(QFrame.NoFrame)
            p = container.palette()
            p.setColor(QPalette.Window, QColor("#ffffff"))
            p.setColor(QPalette.Base, QColor("#ffffff"))
            container.setPalette(p)
            container.setStyleSheet(
                f"background-color: #ffffff; background: #ffffff; "
                f"border: 1px solid {self.border_color}; border-radius: 6px; padding: 0px; margin: 0px;"
            )
