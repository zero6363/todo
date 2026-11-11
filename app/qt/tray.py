"""系统托盘（QSystemTrayIcon + Fluent 圆角菜单）。"""

from __future__ import annotations

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QSystemTrayIcon
from qfluentwidgets import FluentIcon as FIF, SystemTrayMenu


class TrayIcon:
    def __init__(self, icon: QIcon, controller):
        self.controller = controller
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

    def set_today_count(self, count: int) -> None:
        self.count_action.setText(f"今天还有 {count} 项" if count else "今天没有任务")
        self.tray.setToolTip(f"轻待办 · 今日 {count} 项")

    def set_autostart(self, enabled: bool) -> None:
        self.autostart_action.setChecked(bool(enabled))

    def notify(self, title: str, message: str) -> None:
        try:
            self.tray.showMessage(title, message, QSystemTrayIcon.Information, 4000)
        except Exception:
            pass

    def stop(self) -> None:
        self.tray.hide()
