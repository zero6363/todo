"""设置页：用 Fluent 的 SettingCard 组织。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    ComboBox,
    FluentIcon as FIF,
    PushSettingCard,
    SettingCard,
    SettingCardGroup,
    SmoothScrollArea,
    SwitchSettingCard,
    TitleLabel,
)

from .. import autostart, config
from . import theme


class SettingsPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.db = controller.db
        self.setObjectName("page_settings")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 16, 22, 8)
        outer.setSpacing(8)
        outer.addWidget(TitleLabel("设置"))

        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(theme.SCROLL_QSS)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 6, 8, 24)
        self.content_layout.setSpacing(18)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # 提醒
        remind_group = SettingCardGroup("提醒", content)
        self.notify_card = SettingCard(
            FIF.MESSAGE, "提醒方式", "应用内弹窗在屏幕右下角浮出，开着 Windows 免打扰也能看到", remind_group
        )
        combo_host = ComboBox(self.notify_card)
        for label in config.NOTIFY_MODE_LABELS:
            combo_host.addItem(label)
        combo_host.setMinimumWidth(150)
        combo_host.currentIndexChanged.connect(self._on_notify_mode)
        self.notify_card.hBoxLayout.addWidget(combo_host, 0, Qt.AlignRight)
        self.notify_card.hBoxLayout.addSpacing(16)
        self.notify_mode_combo = combo_host

        self.sound_card = SwitchSettingCard(
            FIF.RINGER, "提醒声音", "应用内弹窗时播放一声系统提示音", None, remind_group
        )
        self.sound_card.checkedChanged.connect(
            lambda checked: self._save_switch("notify_sound", checked)
        )

        self.test_card = PushSettingCard(
            "发送", FIF.SEND, "测试提醒", "按当前提醒方式立即演示一次", remind_group
        )
        self.test_card.clicked.connect(controller.test_notification)

        remind_group.addSettingCard(self.notify_card)
        remind_group.addSettingCard(self.sound_card)
        remind_group.addSettingCard(self.test_card)

        # 常规
        general_group = SettingCardGroup("常规", content)
        self.autostart_card = SwitchSettingCard(
            FIF.IOT, "开机自动启动", "登录 Windows 后自动在托盘运行", None, general_group
        )
        self.autostart_card.checkedChanged.connect(self._on_autostart)
        self.tray_card = SwitchSettingCard(
            FIF.MINIMIZE, "关闭窗口时最小化到托盘", "点右上角 × 不退出，继续在后台提醒", None, general_group
        )
        self.tray_card.checkedChanged.connect(
            lambda checked: self._save_switch("close_to_tray", checked)
        )
        self.top_card = SwitchSettingCard(
            FIF.PIN, "窗口置顶", "让主窗口保持在其他窗口上方", None, general_group
        )
        self.top_card.checkedChanged.connect(self._on_topmost)
        general_group.addSettingCard(self.autostart_card)
        general_group.addSettingCard(self.tray_card)
        general_group.addSettingCard(self.top_card)

        # 数据
        data_group = SettingCardGroup("数据", content)
        self.open_card = PushSettingCard(
            "打开", FIF.FOLDER, "数据目录", str(config.data_dir()), data_group
        )
        self.open_card.clicked.connect(lambda: os.startfile(str(config.data_dir())))
        self.clear_card = PushSettingCard(
            "清空", FIF.BROOM, "清理已完成任务", "永久删除所有已完成任务，不可撤销", data_group
        )
        self.clear_card.clicked.connect(controller.clear_completed)
        data_group.addSettingCard(self.open_card)
        data_group.addSettingCard(self.clear_card)

        about_group = SettingCardGroup("关于", content)
        self.about_card = SettingCard(
            FIF.INFO, f"轻待办 v{config.APP_VERSION}", "便携版 · 数据保存在程序目录", about_group
        )
        about_group.addSettingCard(self.about_card)

        for group in (remind_group, general_group, data_group, about_group):
            self.content_layout.addWidget(group)
        self.content_layout.addStretch(1)

    # -------------------------------------------------- 同步状态

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.sync()

    def sync(self) -> None:
        mode = self.db.get_setting("notify_mode", config.DEFAULTS["notify_mode"])
        label = config.NOTIFY_MODE_TITLES.get(mode, config.NOTIFY_MODE_LABELS[0])
        self.notify_mode_combo.blockSignals(True)
        self.notify_mode_combo.setCurrentIndex(config.NOTIFY_MODE_LABELS.index(label))
        self.notify_mode_combo.blockSignals(False)

        self.sound_card.setChecked(self.db.get_setting("notify_sound", "1") == "1")
        self.tray_card.setChecked(self.db.get_setting("close_to_tray", "1") == "1")
        self.top_card.setChecked(self.db.get_setting("always_on_top", "0") == "1")
        self.autostart_card.setChecked(autostart.is_enabled())

    # -------------------------------------------------- 事件

    def _save_switch(self, key: str, checked: bool) -> None:
        self.db.set_setting(key, "1" if checked else "0")

    def _on_notify_mode(self, index: int) -> None:
        label = self.notify_mode_combo.itemText(index)
        mode = config.NOTIFY_MODE_VALUES.get(label, "popup")
        self.db.set_setting("notify_mode", mode)

    def _on_autostart(self, checked: bool) -> None:
        if checked:
            autostart.enable()
        else:
            autostart.disable()
        self.controller.sync_autostart_state()
        if autostart.is_enabled() != checked:
            self.autostart_card.setChecked(autostart.is_enabled())

    def _on_topmost(self, checked: bool) -> None:
        self.db.set_setting("always_on_top", "1" if checked else "0")
        self.controller.set_topmost(checked)
