from __future__ import annotations

from importlib.resources import files

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


def apply_theme(app: QApplication) -> None:
    app.setStyle(QStyleFactory.create("Fusion"))

    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "#17181b",
        QPalette.ColorRole.WindowText: "#e6e7ea",
        QPalette.ColorRole.Base: "#1b1d21",
        QPalette.ColorRole.AlternateBase: "#202227",
        QPalette.ColorRole.Text: "#e6e7ea",
        QPalette.ColorRole.Button: "#2c3036",
        QPalette.ColorRole.ButtonText: "#e6e7ea",
        QPalette.ColorRole.Highlight: "#2f6fed",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#26292e",
        QPalette.ColorRole.ToolTipText: "#e6e7ea",
        QPalette.ColorRole.PlaceholderText: "#6b707a",
        QPalette.ColorRole.Link: "#4f8cff",
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#6b707a"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#6b707a"))
    app.setPalette(palette)

    app.setStyleSheet(files("mqtt_broker.gui").joinpath("theme.qss").read_text(encoding="utf-8"))
