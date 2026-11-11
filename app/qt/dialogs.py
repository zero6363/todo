"""Fluent 对话框：新建/编辑清单、确认框。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget
from qfluentwidgets import (
    CaptionLabel,
    LineEdit,
    MessageBoxBase,
    PushButton,
    SubtitleLabel,
)

from .. import config
from . import theme


class ColorSwatch(QPushButton):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setCheckable(True)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.PointingHandCursor)
        self._refresh()

    def _refresh(self) -> None:
        border = "2px solid #1D2129" if self.isChecked() else "2px solid transparent"
        self.setStyleSheet(
            f"QPushButton {{ background:{self.color};border-radius:13px;border:{border}; }}"
        )

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        self._refresh()


class ListEditDialog(MessageBoxBase):
    def __init__(self, parent=None, title: str = "新建清单", name: str = "", color: str = theme.ACCENT):
        super().__init__(parent)
        self.result: tuple[str, str] | None = None

        self.viewLayout.addWidget(SubtitleLabel(title, self))
        self.name_edit = LineEdit(self)
        self.name_edit.setPlaceholderText("清单名称")
        self.name_edit.setText(name)
        self.viewLayout.addWidget(self.name_edit)

        self.viewLayout.addWidget(CaptionLabel("颜色", self))
        colors = QWidget(self)
        color_layout = QHBoxLayout(colors)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.setSpacing(8)
        self.swatches: list[ColorSwatch] = []
        for item in config.LIST_COLORS:
            swatch = ColorSwatch(item, colors)
            swatch.clicked.connect(lambda _=False, s=swatch: self._pick(s))
            color_layout.addWidget(swatch)
            self.swatches.append(swatch)
        color_layout.addStretch(1)
        self.viewLayout.addWidget(colors)

        self._pick(next((s for s in self.swatches if s.color == color), self.swatches[0]))

        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(400)
        self.name_edit.returnPressed.connect(self.yesButton.click)
        self.name_edit.setFocus()

    def _pick(self, swatch: ColorSwatch) -> None:
        self.current_color = swatch.color
        for item in self.swatches:
            item.setChecked(item is swatch)

    def accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setPlaceholderText("请输入清单名称")
            self.name_edit.setFocus()
            return
        self.result = (name, self.current_color)
        super().accept()


class ConfirmDialog(MessageBoxBase):
    def __init__(self, parent=None, title: str = "确认", content: str = "", ok_text: str = "确定"):
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel(title, self))
        label = CaptionLabel(content, self)
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{theme.TEXT_SUB};")
        self.viewLayout.addWidget(label)
        self.yesButton.setText(ok_text)
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(400)


class SaveChangesDialog(MessageBoxBase):
    """保存 / 放弃 二选一；按取消或 Esc 表示继续编辑。"""

    def __init__(self, parent=None, content: str = "这条任务还有没保存的修改。"):
        super().__init__(parent)
        self.choice = "cancel"
        self.viewLayout.addWidget(SubtitleLabel("有未保存的修改", self))
        label = CaptionLabel(content, self)
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{theme.TEXT_SUB};")
        self.viewLayout.addWidget(label)

        self.yesButton.setText("保存")
        self.cancelButton.setText("放弃修改")
        try:
            self.cancelButton.clicked.disconnect(self._MessageBoxBase__onCancelButtonClicked)
        except (TypeError, AttributeError):
            pass
        self.cancelButton.clicked.connect(self._discard)
        self.widget.setMinimumWidth(420)

    def _discard(self) -> None:
        self.choice = "discard"
        self.reject()

    def accept(self) -> None:
        self.choice = "save"
        super().accept()


class SnoozeDialog(MessageBoxBase):
    """自定义稍后提醒的间隔。"""

    def __init__(self, parent=None, default: int = 10, maximum: int = 10080):
        super().__init__(parent)
        self.minutes: int | None = None
        self.maximum = maximum

        self.viewLayout.addWidget(SubtitleLabel("稍后提醒", self))
        hint = CaptionLabel("多久之后再提醒我？", self)
        hint.setStyleSheet(f"color:{theme.TEXT_SUB};")
        self.viewLayout.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.amount_edit = LineEdit(self)
        self.amount_edit.setValidator(QIntValidator(1, maximum, self))
        self.amount_edit.setText(str(default))
        self.amount_edit.setFixedWidth(88)
        self.amount_edit.setMinimumHeight(32)
        self.amount_edit.setAlignment(Qt.AlignCenter)
        row.addWidget(self.amount_edit)
        unit = CaptionLabel("分钟", self)
        unit.setStyleSheet(f"color:{theme.TEXT_SUB};")
        row.addWidget(unit)
        row.addSpacing(6)
        for label, minutes in config.SNOOZE_OPTIONS:
            button = PushButton(label, self)
            button.setFixedWidth(74)
            button.setMinimumHeight(32)
            button.clicked.connect(lambda _=False, m=minutes: self.amount_edit.setText(str(m)))
            row.addWidget(button)
        row.addStretch(1)
        self.viewLayout.addLayout(row)

        tip = CaptionLabel(f"可填 1 ~ {maximum} 分钟（最长 7 天），也可以点右边的快捷选项", self)
        tip.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        self.viewLayout.addWidget(tip)

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(470)
        self.amount_edit.setFocus()
        self.amount_edit.selectAll()

    def accept(self) -> None:
        try:
            value = int(self.amount_edit.text().strip())
        except ValueError:
            value = 0
        if not 1 <= value <= self.maximum:
            self.amount_edit.setFocus()
            self.amount_edit.selectAll()
            return
        self.minutes = value
        super().accept()


def ask_confirm(parent, title: str, content: str, ok_text: str = "确定") -> bool:
    dialog = ConfirmDialog(parent, title, content, ok_text)
    result = bool(dialog.exec())
    dialog.deleteLater()
    return result


def ask_save_changes(parent) -> str:
    """返回 save / discard / cancel。"""
    dialog = SaveChangesDialog(parent)
    dialog.exec()
    choice = dialog.choice
    dialog.deleteLater()
    return choice


def ask_snooze_minutes(parent, default: int = 10) -> int | None:
    dialog = SnoozeDialog(parent, default=default)
    ok = bool(dialog.exec())
    minutes = dialog.minutes
    dialog.deleteLater()
    return minutes if ok and minutes else None


def ask_list(parent, title: str = "新建清单", name: str = "", color: str = theme.ACCENT):
    dialog = ListEditDialog(parent, title, name, color)
    ok = bool(dialog.exec())
    result = dialog.result
    dialog.deleteLater()
    return result if ok else None
