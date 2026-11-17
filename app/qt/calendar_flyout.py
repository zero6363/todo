"""日期选择浮层。

qfluentwidgets 自带的 CalendarPicker 用 Qt.Popup 弹出日历：窗口未激活、
焦点刚切换、或紧接着上一次弹出的动画时，Popup 会立刻自动关闭，
表现就是「点好几下才弹出来」。这里换成自己管理的 Tool 浮层，
显示/关闭完全由我们控制（点外面或 Esc 才关）。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from qfluentwidgets import CalendarPicker
from qfluentwidgets.components.date_time.calendar_view import CalendarView

_active: "CalendarFlyout | None" = None


def _global_pos(event) -> QPoint | None:
    try:
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        if hasattr(event, "globalPos"):
            return event.globalPos()
    except Exception:
        pass
    return None


class CalendarFlyout(CalendarView):
    """不会因为窗口激活/焦点变化而自己消失的日历浮层。"""

    def __init__(self, anchor):
        super().__init__(anchor.window())
        self._anchor = anchor
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowOpacity(1.0)
        self.setFocusPolicy(Qt.StrongFocus)  # 拿到键盘，Esc 才能作用在日历上
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        win = anchor.window()
        if win is not None:
            win.installEventFilter(self)

    # -------------------------------------------------- 关闭条件

    def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名
        etype = event.type()
        if etype in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            pos = _global_pos(event)
            if pos is not None and self.isVisible():
                inside_self = self.frameGeometry().contains(pos)
                inside_anchor = self._anchor.rect().contains(
                    self._anchor.mapFromGlobal(pos)
                )
                if not inside_self and not inside_anchor:
                    self.close()
        elif etype == QEvent.WindowDeactivate and obj is self._anchor.window():
            self.close()
        elif etype == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.close()
        return False

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def event(self, event) -> bool:
        # 抢在主窗口「Esc 关闭详情」快捷键之前吃掉 Esc
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Escape:
            event.accept()
            return True
        return super().event(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        global _active
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        win = self._anchor.window()
        if win is not None:
            win.removeEventFilter(self)
        if _active is self:
            _active = None
        super().closeEvent(event)

    # -------------------------------------------------- 显示

    def popup_at(self, anchor) -> None:
        hint = self.sizeHint()
        width, height = hint.width() + 5, hint.height()
        pos = anchor.mapToGlobal(
            QPoint(int(anchor.width() / 2 - width / 2), anchor.height() + 4)
        )
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            rect = screen.availableGeometry()
            if pos.y() + height > rect.bottom():
                above = anchor.mapToGlobal(QPoint(0, -height - 4))
                pos.setY(max(rect.top(), above.y()))
            pos.setX(max(rect.left(), min(pos.x(), rect.right() - width)))
        self.move(pos)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)


def open_calendar(anchor, date, on_date_changed, on_reset) -> None:
    """在 anchor 下方打开日历；已打开时再点一次就收起。"""
    global _active
    if _active is not None:
        was_open = False
        try:
            was_open = _active.isVisible()
            _active.close()
        except Exception:
            was_open = False  # 旧浮层已被销毁，直接开新的
        _active = None
        if was_open:
            return

    flyout = CalendarFlyout(anchor)
    flyout.dateChanged.connect(on_date_changed)
    flyout.resetted.connect(on_reset)
    if date is not None and date.isValid():
        flyout.setDate(date)
    _active = flyout
    flyout.popup_at(anchor)


class StableCalendarPicker(CalendarPicker):
    """外观不变，只把弹出的日历换成可控浮层。"""

    def _showCalendarView(self) -> None:  # noqa: N802
        open_calendar(self, self.date, self._onDateChanged, self.reset)
