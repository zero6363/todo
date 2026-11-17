"""日期选择浮层（轻量自绘版）。

背景：qfluentwidgets 的 CalendarView 每次构建要 1 秒以上（年/月/日三个视图
+ 大量样式），点击日期框后要等很久才出现，用户会以为没反应；它还会因为
窗口激活变化瞬间自我关闭。

这里的做法：
- 用 QCalendarWidget 自绘单元格（今日/选中/非本月），外观贴近 Fluent；
- 头部自绘「◀ 2026年11月 ▶」；
- Qt.Popup 浮层，启动时预热 + 全程复用，点下去立即出现；
- 点外部 / Esc / 再点日期框 / 选日期 才关闭。
"""

from __future__ import annotations

from PySide6.QtCore import QDate, QEvent, QLocale, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, CalendarPicker, TransparentToolButton, FluentIcon as FIF

ACCENT = "#00B7C3"
TEXT = "#1D2129"
TEXT_SUB = "#8A9099"
TEXT_DIM = "#C0C4CC"

_flyout: "CalendarFlyout | None" = None


def _dbg(msg: str) -> None:
    import os
    import tempfile
    from pathlib import Path

    if os.environ.get("LIGHTTODO_CAL_DEBUG") != "1":
        return
    try:
        with open(Path(tempfile.gettempdir()) / "lighttodo_cal.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _global_pos(event) -> QPoint | None:
    try:
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        if hasattr(event, "globalPos"):
            return event.globalPos()
    except Exception:
        pass
    return None


class _FluentCalendar(QCalendarWidget):
    """只画数字的月历，选中/今日用 Fluent 风格。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale(QLocale.Chinese, QLocale.China))
        self.setNavigationBarVisible(False)
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.NoHorizontalHeader)
        # 必须允许选中，否则 QCalendarWidget 不会发出 clicked 信号（点击无反应）
        self.setSelectionMode(QCalendarWidget.SingleSelection)
        self.setStyleSheet(
            "QCalendarWidget { background: #FFFFFF; }"
            "QCalendarWidget QTableView { background: #FFFFFF; border: none;"
            " outline: 0; selection-background-color: transparent; }"
            "QCalendarWidget QAbstractItemView:enabled { background: #FFFFFF;"
            f" color: {TEXT}; selection-background-color: transparent; }}"
            "QCalendarWidget QWidget#qt_calendar_calendarview { background: #FFFFFF; }"
        )
        view = self.findChild(QWidget, "qt_calendar_calendarview")
        if view is not None:
            view.setStyleSheet("background: transparent; border: none;")

    def paintCell(self, painter: QPainter, rect: QRect, date: QDate) -> None:  # noqa: N802
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        today = QDate.currentDate()
        selected = self.selectedDate()
        shown = self.monthShown()
        is_selected = date == selected
        if is_selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ACCENT))
            d = min(rect.width(), rect.height()) - 6
            painter.drawEllipse(
                QRect(rect.center().x() - d // 2, rect.center().y() - d // 2, d, d)
            )
            painter.setPen(QColor("#FFFFFF"))
        elif date == today:
            painter.setPen(QColor(ACCENT))
        elif date.month() != shown:
            painter.setPen(QColor(TEXT_DIM))
        else:
            painter.setPen(QColor(TEXT))
        font = QFont(painter.font())
        font.setBold(is_selected or date == today)
        font.setPixelSize(12)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, str(date.day()))
        painter.restore()


class CalendarFlyout(QWidget):
    """可复用的日期浮层。"""

    datePicked = Signal(QDate)

    def __init__(self, parent_window=None):
        super().__init__(parent_window, Qt.Tool)
        self._anchor = None
        self._filter_on = False
        self._closed_at = 0.0
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 11, 14, 13)
        card = QFrame(self)
        card.setObjectName("calCard")
        card.setStyleSheet(
            f"#calCard {{ background:#FFFFFF; border:1px solid #E5E7EB; border-radius:10px; }}"
        )
        outer.addWidget(card)

        body = QVBoxLayout(card)
        body.setContentsMargins(10, 8, 10, 8)
        body.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(4)
        self.prev_btn = TransparentToolButton(FIF.LEFT_ARROW, card)
        self.prev_btn.setFixedSize(28, 28)
        self.title = BodyLabel("", card)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet(f"color:{TEXT}; font-weight:600;")
        self.next_btn = TransparentToolButton(FIF.RIGHT_ARROW, card)
        self.next_btn.setFixedSize(28, 28)
        head.addWidget(self.prev_btn)
        head.addWidget(self.title, 1)
        head.addWidget(self.next_btn)
        body.addLayout(head)

        # 自绘星期表头（避免 QCalendarWidget 默认的灰底红字），宽度与日历对齐
        week_host = QWidget(card)
        week_host.setFixedWidth(266)
        week_row = QHBoxLayout(week_host)
        week_row.setSpacing(0)
        week_row.setContentsMargins(0, 0, 0, 2)
        for text in ("一", "二", "三", "四", "五", "六", "日"):
            label = BodyLabel(text, week_host)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(f"color:{TEXT_SUB}; font-size:11px; background:transparent;")
            week_row.addWidget(label, 1)
        body.addWidget(week_host, 0, Qt.AlignHCenter)

        self.calendar = _FluentCalendar(card)
        self.calendar.setFixedSize(266, 200)
        body.addWidget(self.calendar)

        self.prev_btn.clicked.connect(self._prev_month)
        self.next_btn.clicked.connect(self._next_month)
        self.calendar.clicked.connect(self._on_picked)
        self.calendar.currentPageChanged.connect(lambda *_: self._sync_title())
        self._sync_title()
        self.setFixedWidth(310)

    # -------------------------------------------------- 月份切换

    def _prev_month(self) -> None:
        self.calendar.showPreviousMonth()
        self._sync_title()

    def _next_month(self) -> None:
        self.calendar.showNextMonth()
        self._sync_title()

    def _sync_title(self) -> None:
        self.title.setText(f"{self.calendar.yearShown()}年{self.calendar.monthShown()}月")

    def _on_picked(self, date: QDate) -> None:
        _dbg(f"picked {date.toString('yyyy-MM-dd')}")
        self.close()
        self.datePicked.emit(date)

    # -------------------------------------------------- 关闭条件

    def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名
        etype = event.type()
        if etype in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            pos = _global_pos(event)
            if pos is not None and self.isVisible():
                inside_self = self.frameGeometry().contains(pos)
                inside_anchor = (
                    self._anchor is not None
                    and self._anchor.rect().contains(self._anchor.mapFromGlobal(pos))
                )
                if not inside_self and not inside_anchor:
                    _dbg(f"outside close at {pos} geo={self.frameGeometry().getRect()}")
                    self.close()
        elif etype == QEvent.ShortcutOverride and event.key() == Qt.Key_Escape:
            if self.isVisible():
                event.accept()
                return True  # 别让主窗口的「Esc 关闭详情」抢走
        elif etype == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            if self.isVisible():
                self.close()
                return True
        return False

    def event(self, event) -> bool:
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Escape:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        import time as _t

        self._closed_at = _t.monotonic()
        app = QApplication.instance()
        if app is not None and self._filter_on:
            app.removeEventFilter(self)
            self._filter_on = False
        super().closeEvent(event)

    # -------------------------------------------------- 显示

    def popup_at(self, anchor, date) -> None:
        _dbg(f"popup_at anchor={anchor.mapToGlobal(QPoint(0,0)).toTuple()}")
        self._anchor = anchor
        app = QApplication.instance()
        if app is not None and not self._filter_on:
            app.installEventFilter(self)
            self._filter_on = True
        if date is not None and date.isValid():
            self.calendar.setSelectedDate(date)
            self.calendar.setCurrentPage(date.year(), date.month())
        else:
            today = QDate.currentDate()
            self.calendar.setSelectedDate(today)
            self.calendar.setCurrentPage(today.year(), today.month())
        self._sync_title()

        size = self.sizeHint()
        width, height = size.width(), size.height()
        pos = anchor.mapToGlobal(
            QPoint(int(anchor.width() / 2 - width / 2), anchor.height() + 4)
        )
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            rect = screen.availableGeometry()
            if pos.y() + height > rect.bottom():
                pos.setY(max(rect.top(), anchor.mapToGlobal(QPoint(0, -height - 4)).y()))
            pos.setX(max(rect.left(), min(pos.x(), rect.right() - width)))
        self.move(pos)
        self.show()
        self.raise_()


def _ensure_flyout(anchor) -> CalendarFlyout:
    global _flyout
    try:
        if _flyout is not None:
            return _flyout
    except RuntimeError:
        _flyout = None
    parent = anchor.window() if anchor is not None else None
    _flyout = CalendarFlyout(parent)
    return _flyout


def prewarm(anchor=None) -> None:
    """启动时先把浮层建好（隐藏），第一次点击就能立即出现。"""
    try:
        _ensure_flyout(anchor)
    except Exception:
        pass


def open_calendar(anchor, date, on_date_changed, on_reset=None) -> None:
    """在 anchor 下方打开日历；已打开时再点一次就收起。"""
    import time as _t

    flyout = _ensure_flyout(anchor)
    # Popup 在按下瞬间就会自己关掉，紧接着按钮的 clicked 又会把它打开——
    # 刚关闭的 250ms 内忽略打开请求，保证「再点一次 = 收起」。
    if _t.monotonic() - getattr(flyout, "_closed_at", 0.0) < 0.25:
        return
    if flyout.isVisible():
        flyout.close()
        return
    try:
        flyout.datePicked.disconnect()
    except Exception:
        pass
    if on_date_changed is not None:
        flyout.datePicked.connect(on_date_changed)
    flyout.popup_at(anchor, date)


class StableCalendarPicker(CalendarPicker):
    """外观不变，只把弹出的日历换成快速浮层。"""

    def _showCalendarView(self) -> None:  # noqa: N802
        open_calendar(self, self.date, self._onDateChanged, self.reset)
