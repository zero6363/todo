"""系统托盘（QSystemTrayIcon + Fluent 圆角菜单）。

托盘图标右下角带红色角标，显示今天未完成任务数。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QSystemTrayIcon
from qfluentwidgets import FluentIcon as FIF, SystemTrayMenu

BADGE_COLOR = "#c42b1c"  # Fluent 红
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64)


def _draw_badge(painter: QPainter, rect: QRect, text: str) -> None:
    """在 rect 内画红色圆 + 白色数字。"""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(BADGE_COLOR))
    painter.drawEllipse(rect)
    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI")
    if len(text) <= 1:
        ratio = 0.72
    elif len(text) == 2:
        ratio = 0.62
    else:
        ratio = 0.46
    font.setPixelSize(max(5, int(rect.height() * ratio)))
    font.setBold(True)
    font.setStyleStrategy(QFont.PreferAntialias)
    # 小尺寸下稍微上移，避免数字底边被裁切
    body = QRect(rect.x(), rect.y() - max(1, rect.height() // 12), rect.width(), rect.height())
    painter.setFont(font)
    painter.drawText(body, Qt.AlignCenter, text)
    painter.restore()


class TrayIcon:
    def __init__(self, icon: QIcon, controller):
        self.controller = controller
        self._base_icon = icon
        self._count = -1
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("轻待办")

        self.menu = SystemTrayMenu()
        self.open_action = QAction(FIF.HOME.icon(), "打开轻待办", self.menu)
        self.open_action.triggered.connect(controller.show_window)
        self.menu.addAction(self.open_action)

        self.count_action = QAction("今天没有任务", self.menu)
        self.count_action.setEnabled(False)
        self.menu.addAction(self.count_action)
        self.menu.addSeparator()

        self.new_action = QAction(FIF.ADD.icon(), "新建任务", self.menu)
        self.new_action.triggered.connect(controller.new_task)
        self.menu.addAction(self.new_action)

        self.autostart_action = QAction("开机自动启动", self.menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.triggered.connect(controller.toggle_autostart)
        self.menu.addAction(self.autostart_action)
        self.menu.addSeparator()

        self.quit_action = QAction(FIF.POWER_BUTTON.icon(), "退出", self.menu)
        self.quit_action.triggered.connect(controller.quit_app)
        self.menu.addAction(self.quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.controller.show_window()

    # -------------------------------------------------- 角标图标

    def _badged_icon(self, count: int) -> QIcon:
        """按多个尺寸生成带红圈数字的托盘图标，Windows 会挑选最合适的一档。"""
        icon = QIcon()
        text = str(count) if count <= 99 else "99+"
        for size in ICON_SIZES:
            base = self._base_icon.pixmap(size, size)
            if base.isNull():
                continue
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(0, 0, base)
            side = max(7, int(round(size * (0.72 if size <= 20 else 0.62))))
            rect = QRect(size - side, size - side, side, side)
            _draw_badge(painter, rect, text)
            painter.end()
            icon.addPixmap(pix)
        return icon if not icon.isNull() else self._base_icon

    def set_today_count(self, count: int) -> None:
        count = max(0, int(count))
        self.count_action.setText(f"今天还有 {count} 项" if count else "今天没有任务")
        self.tray.setToolTip(f"轻待办 · 今日 {count} 项")
        if count == self._count:
            return
        self._count = count
        try:
            self.tray.setIcon(self._badged_icon(count) if count > 0 else self._base_icon)
        except Exception:
            pass

    def set_autostart(self, enabled: bool) -> None:
        self.autostart_action.setChecked(bool(enabled))

    def notify(self, title: str, message: str) -> None:
        try:
            self.tray.showMessage(title, message, QSystemTrayIcon.Information, 4000)
        except Exception:
            pass

    def stop(self) -> None:
        self.tray.hide()
