"""Fluent 主题：颜色、样式片段、图标。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from qfluentwidgets import Theme, qconfig, setTheme, setThemeColor

ACCENT = "#3A6FF7"
ACCENT_HOVER = "#2B5EE2"
ACCENT_SOFT = "#EAF1FF"
DANGER = "#E5484D"
DANGER_SOFT = "#FDECEC"
WARN = "#E8833A"
SUCCESS = "#13935A"
TEXT = "#1D2129"
TEXT_SUB = "#5C6470"
TEXT_MUTED = "#9AA3AE"
BORDER = "#E6E8EC"
HOVER = "#F3F5F8"
SELECTED = "#EEF4FF"
PANEL = "#FBFBFC"

PRIORITY_COLORS = {0: "", 1: "#4C9AFF", 2: "#F5A524", 3: "#E5484D"}
PRIORITY_NAMES = {0: "无", 1: "低", 2: "中", 3: "高"}


def apply_theme() -> None:
    setTheme(Theme.LIGHT)
    setThemeColor(ACCENT)
    qconfig.set(qconfig.themeMode, Theme.LIGHT)
    _localize_calendar()


def _localize_calendar() -> None:
    """qfluentwidgets 的日历星期表头写死成 Mo/Tu…，换成中文。"""
    from qfluentwidgets.components.date_time.calendar_view import DayScrollView

    if getattr(DayScrollView, "_zh_weekdays", False):
        return
    original_init = DayScrollView.__init__

    def patched(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.weekDays = list("一二三四五六日")
        for index in range(self.weekDayLayout.count()):
            item = self.weekDayLayout.itemAt(index)
            label = item.widget() if item else None
            if label is not None and index < 7:
                label.setText(self.weekDays[index])

    DayScrollView.__init__ = patched
    DayScrollView._zh_weekdays = True


def dot_icon(color: str, size: int = 16) -> QIcon:
    """清单用的彩色圆点图标。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(4, 4, size - 8, size - 8)
    painter.end()
    return QIcon(pixmap)


def chip_style(color: str, background: str) -> str:
    return (
        f"color:{color};background:{background};border-radius:5px;"
        "padding:2px 8px;font-size:9pt;"
    )


TASK_ROW_QSS = f"""
#taskRow {{ background: transparent; border-radius: 8px; }}
#taskRow:hover {{ background: {HOVER}; }}
#taskRow[selected="true"] {{ background: {SELECTED}; }}
"""

SCROLL_QSS = """
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
"""


REPEAT = "#8B5CF6"
