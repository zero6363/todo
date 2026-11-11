"""屏幕右下角的 Fluent 提醒卡片。"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    DropDownPushButton,
    FluentIcon as FIF,
    PrimaryPushButton,
    RoundMenu,
    TransparentToolButton,
)

from .. import config, utils
from . import dialogs, theme

CARD_WIDTH = 380
CARD_HEIGHT = 180
QUEUE_BAR_HEIGHT = 26


class ReminderPopup(QWidget):
    closed = Signal(object)

    def __init__(
        self,
        task,
        index: int = 0,
        on_complete=None,
        on_snooze=None,
        parent=None,
        dialog_parent=None,
    ):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.task = task
        self.task_id = int(task["id"])
        self._on_complete = on_complete
        self._on_snooze = on_snooze
        self._dialog_parent = dialog_parent
        self._closing = False

        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        card = QFrame(self)
        card.setObjectName("reminderCard")
        card.setStyleSheet(
            f"#reminderCard {{ background: #FFFFFF; border: 1px solid {theme.BORDER};"
            " border-radius: 10px; }}"
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 60))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(0)

        accent = QFrame()
        accent.setFixedWidth(4)
        accent.setStyleSheet(
            f"background:{self._accent_color(task)};border-top-left-radius:10px;border-bottom-left-radius:10px;"
        )
        layout.addWidget(accent)

        content = QVBoxLayout()
        content.setContentsMargins(14, 10, 0, 14)
        content.setSpacing(4)
        layout.addLayout(content, 1)

        top = QHBoxLayout()
        top.setSpacing(6)
        tag = CaptionLabel("任务提醒")
        tag.setStyleSheet(f"color:{theme.ACCENT};font-weight:600;")
        top.addWidget(tag)
        top.addStretch(1)
        close_button = TransparentToolButton(FIF.CLOSE)
        close_button.setFixedSize(24, 24)
        close_button.clicked.connect(self.close)
        top.addWidget(close_button)
        content.addLayout(top)

        title = BodyLabel(utils.truncate(task["title"], 44))
        font = title.font()
        font.setPointSize(10)
        font.setBold(True)
        title.setFont(font)
        content.addWidget(title)

        meta = utils.describe_due(task["due_date"], task["due_time"])
        if task["list_name"]:
            meta = f"{meta} · {task['list_name']}"
        meta_label = CaptionLabel(meta)
        meta_label.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        content.addWidget(meta_label)

        content.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        done = PrimaryPushButton("完成")
        done.setFixedSize(66, 28)
        done.clicked.connect(self._complete)
        buttons.addWidget(done)

        self.snooze_button = DropDownPushButton("稍后")
        self.snooze_button.setFixedSize(100, 28)
        snooze_menu = RoundMenu("", self.snooze_button)
        for label, minutes in config.SNOOZE_OPTIONS:
            snooze_menu.addAction(
                Action(
                    icon=FIF.STOP_WATCH,
                    text=label,
                    triggered=lambda _=False, m=minutes: self._snooze(m),
                )
            )
        snooze_menu.addSeparator()
        snooze_menu.addAction(
            Action(icon=FIF.EDIT, text="自定义…", triggered=self._custom_snooze)
        )
        self.snooze_button.setMenu(snooze_menu)
        buttons.addWidget(self.snooze_button)
        buttons.addStretch(1)
        content.addLayout(buttons)

        self.queue_label = CaptionLabel("")
        self.queue_label.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        self.queue_label.hide()
        content.addWidget(self.queue_label)

        self._place(index)
        self._fade_in()
        self._auto_close = QTimer(self)
        self._auto_close.setSingleShot(True)
        self._auto_close.timeout.connect(self.close)
        self._auto_close.start(120000)

    def set_queue_count(self, count: int) -> None:
        """折叠显示还排着多少条提醒。"""
        if count > 0:
            self.queue_label.setText(f"另有 {count} 条提醒排队，处理完自动出现")
            self.queue_label.show()
            height = CARD_HEIGHT + QUEUE_BAR_HEIGHT
        else:
            self.queue_label.hide()
            height = CARD_HEIGHT
        if self.height() != height:
            self.setFixedSize(CARD_WIDTH, height)

    @staticmethod
    def _accent_color(task) -> str:
        try:
            return task["list_color"] or theme.ACCENT
        except (KeyError, IndexError):
            return theme.ACCENT

    def _place(self, index: int) -> None:
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = area.right() - CARD_WIDTH - 8
        y = area.bottom() - (index + 1) * (self.height() + 4) - 4
        self.move(QPoint(max(area.left(), x), max(area.top(), y)))

    def _fade_in(self) -> None:
        self.setWindowOpacity(0.0)
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(180)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(lambda: self.setWindowOpacity(1.0))
        # 必须留一个引用：局部变量被回收会连带删掉动画，卡片就永远停在透明状态
        self._fade_animation = animation
        animation.start()
        # 兜底：万一动画没跑起来，也要保证能看见
        QTimer.singleShot(500, lambda: self.setWindowOpacity(1.0))

    def _complete(self) -> None:
        if self._on_complete:
            self._on_complete(self.task_id)
        self.close()

    def _snooze(self, minutes: int = config.SNOOZE_DEFAULT) -> None:
        if self._on_snooze:
            self._on_snooze(self.task_id, int(minutes))
        self.close()

    def _custom_snooze(self) -> None:
        self._auto_close.stop()
        minutes = dialogs.ask_snooze_minutes(self._dialog_parent or self, config.SNOOZE_DEFAULT)
        if minutes:
            self._snooze(minutes)
        elif not self._closing:
            self._auto_close.start(120000)

    def closeEvent(self, event) -> None:
        if not self._closing:
            self._closing = True
            self.closed.emit(self)
        super().closeEvent(event)
