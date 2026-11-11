"""Fluent 任务行、日期胶囊、空状态等基础控件。"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, CheckBox, FluentIcon as FIF, IconWidget, PrimaryPushButton

from .. import utils
from . import theme


class ChipLabel(QLabel):
    def __init__(self, text: str, color: str, background: str = "transparent", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(theme.chip_style(color, background))
        self.setAlignment(Qt.AlignCenter)


def due_chip_style(task) -> tuple[str, str, str]:
    due_date = task["due_date"]
    if not due_date:
        return "", "", theme.TEXT_MUTED
    text = utils.describe_due(due_date, task["due_time"])
    if task["completed"]:
        return text, theme.TEXT_MUTED, "transparent"
    if utils.is_overdue(due_date, task["due_time"]):
        return text, theme.DANGER, theme.DANGER_SOFT
    if due_date == utils.today().isoformat():
        return text, theme.ACCENT, theme.ACCENT_SOFT
    return text, theme.TEXT_SUB, "transparent"


class TaskRow(QFrame):
    """任务列表中的一行。"""

    toggled = Signal(int)
    opened = Signal(int)
    menu_requested = Signal(int, QPoint)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.task_id = int(task["id"])
        self.completed = bool(task["completed"])

        self.setObjectName("taskRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(62)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(theme.TASK_ROW_QSS)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menu_requested.emit(self.task_id, self.mapToGlobal(pos))
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 9, 14, 9)
        layout.setSpacing(10)

        priority = int(task["priority"] or 0)
        bar = QFrame()
        bar.setFixedWidth(3)
        bar.setStyleSheet(
            f"background:{theme.PRIORITY_COLORS.get(priority) or 'transparent'};border-radius:1px;"
        )
        layout.addWidget(bar)

        self.checkbox = CheckBox()
        self.checkbox.setChecked(self.completed)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.checkStateChanged.connect(self._on_state_changed)
        layout.addWidget(self.checkbox, 0, Qt.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        text_box.setContentsMargins(0, 0, 0, 0)

        self.title_label = BodyLabel(utils.truncate(task["title"], 70))
        font = self.title_label.font()
        font.setPointSize(10)
        font.setBold(True)
        self.title_label.setFont(font)
        if self.completed:
            self.title_label.setStyleSheet(f"color:{theme.TEXT_MUTED};text-decoration:line-through;")
        text_box.addWidget(self.title_label)

        meta = self._meta_text(task)
        self.meta_label = CaptionLabel(meta)
        self.meta_label.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        if meta:
            text_box.addWidget(self.meta_label)
        layout.addLayout(text_box, 1)

        chip_text, chip_color, chip_bg = due_chip_style(task)
        if chip_text:
            layout.addWidget(ChipLabel(chip_text, chip_color, chip_bg), 0, Qt.AlignVCenter)

    # -------------------------------------------------- 内部

    @staticmethod
    def _meta_text(task) -> str:
        parts = []
        if task["list_name"]:
            parts.append(task["list_name"])
        repeat = utils.repeat_label(task["repeat_rule"])
        if repeat:
            parts.append(repeat)
        if (task["notes"] or "").strip():
            parts.append("有备注")
        if int(task["defer_count"] or 0) > 0:
            # 显示延期到了哪一天，而不是只给一个次数
            target = utils.describe_due(task["due_date"], task["due_time"])
            parts.append(f"已延期 {int(task['defer_count'])} 次 · 延期至 {target}")
        return " · ".join(parts)

    def _on_state_changed(self, state) -> None:
        checked = state == Qt.CheckState.Checked
        if checked != self.completed:
            self.toggled.emit(self.task_id)

    def set_selected(self, value: bool) -> None:
        self.setProperty("selected", "true" if value else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    # -------------------------------------------------- 交互

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.opened.emit(self.task_id)
        super().mouseReleaseEvent(event)


class EmptyState(QWidget):
    def __init__(self, title: str, hint: str, action_text: str = "", on_action: Callable | None = None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 70, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        icon = IconWidget(FIF.CHECKBOX)
        icon.setFixedSize(56, 56)
        effect = QGraphicsOpacityEffect(icon)
        effect.setOpacity(0.3)
        icon.setGraphicsEffect(effect)
        layout.addWidget(icon, 0, Qt.AlignHCenter)

        title_label = BodyLabel(title)
        font = title_label.font()
        font.setPointSize(11)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setStyleSheet(f"color:{theme.TEXT_SUB};")
        layout.addWidget(title_label, 0, Qt.AlignHCenter)

        hint_label = CaptionLabel(hint)
        hint_label.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        layout.addWidget(hint_label, 0, Qt.AlignHCenter)

        if action_text and on_action:
            button = PrimaryPushButton(action_text)
            button.setFixedWidth(110)
            button.clicked.connect(on_action)
            layout.addSpacing(6)
            layout.addWidget(button, 0, Qt.AlignHCenter)

        layout.addStretch(1)
