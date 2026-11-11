"""任务详情面板：日期 / 时间选择器 + 手动输入推断 + 保存取消。"""

from __future__ import annotations

from datetime import date, timedelta

from html import escape

from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CalendarPicker,
    CaptionLabel,
    CheckBox,
    ComboBox,
    FluentIcon as FIF,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SegmentedWidget,
    SmoothScrollArea,
    StrongBodyLabel,
    TextEdit,
    TimePicker,
    TransparentToolButton,
)

from .. import config, utils
from . import theme

MANUAL_PLACEHOLDER = "手动输入：明天十点 / 11-20 15:30 / 1小时后"
MANUAL_FAILED = "没识别出来，试试「明天十点」「1小时后」「11-20 15:30」"
INBOX_HINT = "未设置日期，任务会留在收集箱"


class DetailPanel(QFrame):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.db = controller.db
        self.task_id: int | None = None
        self._loading = False
        self._has_date = False
        self._snapshot: dict | None = None

        self.setFixedWidth(372)
        self.setStyleSheet(
            f"DetailPanel {{ background: {theme.PANEL}; border-left: 1px solid {theme.BORDER}; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -------------------------------------------------- 顶部
        head_host = QWidget(self)
        head = QHBoxLayout(head_host)
        head.setContentsMargins(18, 12, 10, 6)
        head.addWidget(StrongBodyLabel("任务详情"), 1)
        close_button = TransparentToolButton(FIF.CLOSE)
        close_button.clicked.connect(lambda: controller.close_detail())
        head.addWidget(close_button)
        outer.addWidget(head_host)

        # -------------------------------------------------- 滚动内容
        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(theme.SCROLL_QSS)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 0, 12, 12)
        layout.setSpacing(6)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll, 1)

        self.title_edit = TextEdit()
        self.title_edit.setFixedHeight(62)
        self.title_edit.setPlaceholderText("任务标题")
        self.title_edit.setStyleSheet(
            f"TextEdit {{ background: transparent; border: none; color: {theme.TEXT}; }}"
        )
        font = self.title_edit.font()
        font.setPointSize(12)
        font.setBold(True)
        self.title_edit.setFont(font)
        self.title_edit.textChanged.connect(self._on_edit)
        layout.addWidget(self.title_edit)

        # 清单
        layout.addWidget(self._label("清单"))
        self.list_combo = ComboBox()
        self.list_combo.currentIndexChanged.connect(self._on_edit)
        layout.addWidget(self.list_combo)

        # 截止日期
        layout.addWidget(self._label("截止日期"))
        date_row = QHBoxLayout()
        date_row.setSpacing(5)
        self.calendar = CalendarPicker()
        self.calendar.dateChanged.connect(self._on_date_changed)
        date_row.addWidget(self.calendar, 1)
        for text, delta in (("今天", 0), ("明天", 1)):
            button = PushButton(text)
            button.setFixedWidth(50)
            button.clicked.connect(lambda _=False, d=delta: self._quick_date(d))
            date_row.addWidget(button)
        clear_button = PushButton("清除")
        clear_button.setFixedWidth(50)
        clear_button.clicked.connect(self._clear_date)
        date_row.addWidget(clear_button)
        layout.addLayout(date_row)

        # 手动输入（文本推断）
        manual_row = QHBoxLayout()
        manual_row.setSpacing(6)
        self.manual_edit = LineEdit()
        self.manual_edit.setPlaceholderText(MANUAL_PLACEHOLDER)
        self.manual_edit.setClearButtonEnabled(True)
        self.manual_edit.setMinimumHeight(32)
        self.manual_edit.textChanged.connect(self._on_manual_changed)
        self.manual_edit.returnPressed.connect(self._apply_manual)
        manual_row.addWidget(self.manual_edit, 1)
        self.manual_button = PushButton("套用")
        self.manual_button.setFixedWidth(52)
        self.manual_button.setMinimumHeight(32)
        self.manual_button.clicked.connect(self._apply_manual)
        manual_row.addWidget(self.manual_button)
        layout.addLayout(manual_row)

        self.date_hint = CaptionLabel("")
        self.date_hint.setTextFormat(Qt.RichText)
        self.date_hint.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        self.date_hint.setWordWrap(True)
        layout.addWidget(self.date_hint)

        # 时间
        layout.addWidget(self._label("时间"))
        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        self.time_picker = TimePicker(showSeconds=False)
        self.time_picker.setTime(QTime(config.DEFAULT_DUE_HOUR, 0))
        self.time_picker.setMinimumWidth(150)
        self.time_picker.timeChanged.connect(self._on_time_changed)
        time_row.addWidget(self.time_picker)
        self.all_day = CheckBox("全天")
        self.all_day.setChecked(False)
        self.all_day.checkStateChanged.connect(self._on_all_day_changed)
        time_row.addWidget(self.all_day)
        time_row.addStretch(1)
        layout.addLayout(time_row)

        # 提醒
        layout.addWidget(self._label("提醒"))
        self.remind_combo = ComboBox()
        self.remind_combo.addItems(config.REMIND_LABELS)
        self.remind_combo.currentIndexChanged.connect(self._on_edit)
        layout.addWidget(self.remind_combo)

        # 重复
        layout.addWidget(self._label("重复"))
        self.repeat_combo = ComboBox()
        for label, rule in config.REPEAT_OPTIONS:
            self.repeat_combo.addItem(label, userData=rule)
        self.repeat_combo.currentIndexChanged.connect(self._on_repeat_changed)
        layout.addWidget(self.repeat_combo)

        # 优先级
        layout.addWidget(self._label("优先级"))
        self.priority_seg = SegmentedWidget()
        for level, name in config.PRIORITY_NAMES.items():
            self.priority_seg.addItem(str(level), name)
        self.priority_seg.currentItemChanged.connect(self._on_edit)
        layout.addWidget(self.priority_seg)

        # 备注
        layout.addWidget(self._label("备注"))
        self.notes_edit = TextEdit()
        self.notes_edit.setPlaceholderText("添加备注…")
        self.notes_edit.setFixedHeight(104)
        self.notes_edit.textChanged.connect(self._on_edit)
        layout.addWidget(self.notes_edit)

        self.info_label = CaptionLabel("")
        self.info_label.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        extra = QHBoxLayout()
        extra.setSpacing(8)
        self.complete_button = PushButton("标记完成")
        self.complete_button.clicked.connect(self._toggle_complete)
        extra.addWidget(self.complete_button)
        extra.addStretch(1)
        delete_button = PushButton("删除任务")
        delete_button.setStyleSheet(f"color:{theme.DANGER};")
        delete_button.clicked.connect(self._delete)
        extra.addWidget(delete_button)
        layout.addLayout(extra)
        layout.addStretch(1)

        # -------------------------------------------------- 底部保存栏
        divider = QFrame(self)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background:{theme.BORDER};")
        outer.addWidget(divider)

        footer = QWidget(self)
        footer.setStyleSheet("background: transparent;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 10, 12, 12)
        footer_layout.setSpacing(8)
        self.status_label = CaptionLabel("")
        self.status_label.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        footer_layout.addWidget(self.status_label, 1)
        self.cancel_button = PushButton("取消")
        self.cancel_button.setFixedWidth(62)
        self.cancel_button.clicked.connect(self._cancel)
        footer_layout.addWidget(self.cancel_button)
        self.save_button = PrimaryPushButton("保存")
        self.save_button.setFixedWidth(78)
        self.save_button.clicked.connect(self._on_save_clicked)
        footer_layout.addWidget(self.save_button)
        outer.addWidget(footer)

    # -------------------------------------------------- 构建辅助

    @staticmethod
    def _label(text: str) -> CaptionLabel:
        label = CaptionLabel(text)
        label.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        return label

    # -------------------------------------------------- 载入

    @staticmethod
    def _task_values(task) -> dict:
        return {
            "title": (task["title"] or "").strip(),
            "notes": (task["notes"] or "").strip(),
            "due_date": task["due_date"],
            "due_time": task["due_time"],
            "remind_offset": task["remind_offset"],
            "priority": int(task["priority"] or 0),
            "list_id": int(task["list_id"]) if task["list_id"] is not None else None,
            "repeat_rule": task["repeat_rule"],
        }

    def load(self, task_id: int, discard: bool = False) -> None:
        """载入任务；若有未保存改动会先落库，避免被覆盖。"""
        if not discard and self.is_dirty():
            self.save()
        task = self.db.get_task(task_id)
        if task is None:
            return
        self._loading = True
        try:
            self.task_id = task_id
            self.title_edit.blockSignals(True)
            self.title_edit.setPlainText(task["title"])
            self.title_edit.blockSignals(False)

            self._reload_lists(task["list_name"])

            due_date = task["due_date"]
            self._has_date = bool(due_date)
            if due_date:
                year, month, day = (int(part) for part in due_date.split("-"))
                self.calendar.blockSignals(True)
                self.calendar.setDate(QDate(year, month, day))
                self.calendar.blockSignals(False)

            due_time = task["due_time"]
            self.time_picker.blockSignals(True)
            self.all_day.blockSignals(True)
            if due_time:
                hour, minute = (int(part) for part in due_time.split(":"))
                self.time_picker.setTime(QTime(hour, minute))
                self.all_day.setChecked(False)
                self.time_picker.setEnabled(True)
            else:
                self.time_picker.setTime(QTime(config.DEFAULT_DUE_HOUR, 0))
                self.all_day.setChecked(True)
                self.time_picker.setEnabled(False)
            self.time_picker.blockSignals(False)
            self.all_day.blockSignals(False)

            offset = task["remind_offset"]
            label = next((name for name, value in config.REMIND_OPTIONS if value == offset), "不提醒")
            self.remind_combo.blockSignals(True)
            self.remind_combo.setCurrentIndex(config.REMIND_LABELS.index(label))
            self.remind_combo.blockSignals(False)

            self.repeat_combo.blockSignals(True)
            self.repeat_combo.setCurrentIndex(self._repeat_index(task["repeat_rule"]))
            self.repeat_combo.blockSignals(False)

            self.priority_seg.blockSignals(True)
            self.priority_seg.setCurrentItem(str(int(task["priority"] or 0)))
            self.priority_seg.blockSignals(False)

            self.notes_edit.blockSignals(True)
            self.notes_edit.setPlainText(task["notes"] or "")
            self.notes_edit.blockSignals(False)

            self.manual_edit.blockSignals(True)
            self.manual_edit.clear()
            self.manual_edit.blockSignals(False)

            self._snapshot = self._task_values(task)
            self._refresh_hints(task)
            self._update_dirty_ui()
            self.status_label.setText("")
        finally:
            self._loading = False

    def _reload_lists(self, current: str | None) -> None:
        self.list_combo.blockSignals(True)
        self.list_combo.clear()
        names = [row["name"] for row in self.db.lists()]
        self.list_combo.addItems(names)
        if current in names:
            self.list_combo.setCurrentIndex(names.index(current))
        self.list_combo.blockSignals(False)

    def _refresh_hints(self, task=None) -> None:
        manual = self.manual_edit.text().strip()
        if manual:
            parsed = utils.parse_quick_input(manual)
            if parsed["due_date"] or parsed["due_time"]:
                bits = []
                if parsed["matched"]:
                    bits.append(
                        f"<span style='color:{theme.ACCENT};font-weight:600'>"
                        f"{escape(parsed['matched'])}</span>"
                    )
                if parsed["repeat_label"]:
                    bits.append(
                        f"<span style='color:{theme.REPEAT};font-weight:600'>"
                        f"{escape(parsed['repeat_label'])}</span>"
                    )
                joined = f"<span style='color:{theme.TEXT_MUTED}'> · </span>".join(bits)
                self.date_hint.setText(
                    f"<span style='color:{theme.TEXT_MUTED}'>识别到 </span>{joined}"
                    f"<span style='color:{theme.TEXT_MUTED}'>，回车套用</span>"
                )
            else:
                self.date_hint.setText(MANUAL_FAILED)
            self.date_hint.show()
        elif not self._has_date:
            self.date_hint.setText(INBOX_HINT)
            self.date_hint.show()
        else:
            self.date_hint.hide()

        if task is None and self.task_id:
            task = self.db.get_task(self.task_id)
        if task is None:
            return
        info = f"创建于 {utils.fmt_created(task['created_at'])}"
        deferred = int(task["defer_count"] or 0)
        if deferred:
            info += f" · 已自动延期 {deferred} 次"
            target = utils.describe_due(task["due_date"], task["due_time"])
            info += f"（延期至 {target}"
            info += f"，原定 {task['orig_due_date']}）" if task["orig_due_date"] else "）"
        elif task["orig_due_date"]:
            info += f"（原定 {task['orig_due_date']}）"
        repeat_text = utils.repeat_label(task["repeat_rule"])
        if repeat_text:
            info += f" · {repeat_text}，完成后自动生成下一次"
        self.info_label.setText(info)
        self.complete_button.setText("标记为未完成" if task["completed"] else "标记完成")

    # -------------------------------------------------- 当前值与脏状态

    def _current_values(self) -> dict:
        due_date = None
        if self._has_date:
            qdate = self.calendar.getDate()
            due_date = f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"
        due_time = None
        if due_date and not self.all_day.isChecked():
            qtime = self.time_picker.getTime()
            due_time = f"{qtime.hour():02d}:{qtime.minute():02d}"

        list_name = self.list_combo.currentText()
        list_id = next(
            (int(row["id"]) for row in self.db.lists() if row["name"] == list_name), None
        )
        route = self.priority_seg.currentRouteKey()
        return {
            "title": self.title_edit.toPlainText().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
            "due_date": due_date,
            "due_time": due_time,
            "remind_offset": config.REMIND_VALUES.get(self.remind_combo.currentText()),
            "priority": int(route) if route not in (None, "") else 0,
            "list_id": list_id,
            "repeat_rule": self.repeat_combo.currentData(),
        }

    def is_dirty(self) -> bool:
        if self.task_id is None or self._snapshot is None:
            return False
        return self._current_values() != self._snapshot

    def _update_dirty_ui(self) -> None:
        dirty = self.is_dirty()
        self.save_button.setEnabled(dirty)
        self.cancel_button.setEnabled(True)
        if dirty:
            self.status_label.setText("未保存的修改")
            self.status_label.setStyleSheet(f"color:{theme.WARN};")
        elif self.status_label.text() == "未保存的修改":
            self.status_label.setText("")
            self.status_label.setStyleSheet(f"color:{theme.TEXT_MUTED};")

    # -------------------------------------------------- 交互

    def _on_edit(self) -> None:
        if self._loading:
            return
        self._update_dirty_ui()

    def _on_list_changed(self, _index: int) -> None:
        self._on_edit()

    def _on_date_changed(self, _date: QDate) -> None:
        if self._loading:
            return
        self._has_date = True
        if self.all_day.isChecked():
            # 选了具体日期就默认给 15:00，符合「不加时间默认 15 点」
            self.all_day.blockSignals(True)
            self.all_day.setChecked(False)
            self.all_day.blockSignals(False)
            self.time_picker.setEnabled(True)
        self._refresh_hints()
        self._on_edit()

    def _on_time_changed(self, _time: QTime) -> None:
        if self._loading:
            return
        if self.all_day.isChecked():
            self.all_day.blockSignals(True)
            self.all_day.setChecked(False)
            self.all_day.blockSignals(False)
        self.time_picker.setEnabled(True)
        self._refresh_hints()
        self._on_edit()

    def _on_all_day_changed(self, state) -> None:
        if self._loading:
            return
        checked = state == Qt.CheckState.Checked
        self.time_picker.setEnabled(not checked)
        self._on_edit()

    def _on_manual_changed(self, _text: str) -> None:
        if self._loading:
            return
        self._refresh_hints()

    def _apply_manual(self) -> None:
        text = self.manual_edit.text().strip()
        if not text:
            return
        parsed = utils.parse_quick_input(text)
        if not (parsed["due_date"] or parsed["due_time"]):
            self.date_hint.setText(MANUAL_FAILED)
            self.date_hint.show()
            return

        if parsed["due_date"]:
            year, month, day = (int(part) for part in parsed["due_date"].split("-"))
            self.calendar.blockSignals(True)
            self.calendar.setDate(QDate(year, month, day))
            self.calendar.blockSignals(False)
            self._has_date = True

        if parsed["due_time"]:
            hour, minute = (int(part) for part in parsed["due_time"].split(":"))
            self.time_picker.blockSignals(True)
            self.time_picker.setTime(QTime(hour, minute))
            self.time_picker.blockSignals(False)
            self.all_day.blockSignals(True)
            self.all_day.setChecked(False)
            self.all_day.blockSignals(False)
            self.time_picker.setEnabled(True)
        elif self.all_day.isChecked():
            # 只识别出日期：按默认 15:00 处理
            self.all_day.blockSignals(True)
            self.all_day.setChecked(False)
            self.all_day.blockSignals(False)
            self.time_picker.setEnabled(True)

        self.manual_edit.blockSignals(True)
        self.manual_edit.clear()
        self.manual_edit.blockSignals(False)
        self._refresh_hints()
        self._on_edit()

    def _repeat_index(self, rule: str | None) -> int:
        if not rule:
            return 0
        for index in range(self.repeat_combo.count()):
            if self.repeat_combo.itemData(index) == rule:
                return index
        self.repeat_combo.addItem(utils.repeat_label(rule), userData=rule)
        return self.repeat_combo.count() - 1

    def _on_repeat_changed(self, _index: int) -> None:
        if self._loading:
            return
        if self.repeat_combo.currentData() and not self._has_date:
            # 循环任务必须有日期，没设置就落到今天
            target = date.today()
            self.calendar.blockSignals(True)
            self.calendar.setDate(QDate(target.year, target.month, target.day))
            self.calendar.blockSignals(False)
            self._has_date = True
            if self.all_day.isChecked():
                self.all_day.blockSignals(True)
                self.all_day.setChecked(False)
                self.all_day.blockSignals(False)
                self.time_picker.setEnabled(True)
            self._refresh_hints()
        self._on_edit()

    def _quick_date(self, delta: int) -> None:
        target = date.today() + timedelta(days=delta)
        self.calendar.blockSignals(True)
        self.calendar.setDate(QDate(target.year, target.month, target.day))
        self.calendar.blockSignals(False)
        self._has_date = True
        if self.all_day.isChecked():
            self.all_day.blockSignals(True)
            self.all_day.setChecked(False)
            self.all_day.blockSignals(False)
            self.time_picker.setEnabled(True)
        self._refresh_hints()
        self._on_edit()

    def _clear_date(self) -> None:
        self._has_date = False
        self.all_day.blockSignals(True)
        self.all_day.setChecked(True)
        self.all_day.blockSignals(False)
        self.time_picker.setEnabled(False)
        self._refresh_hints()
        self._on_edit()

    def _toggle_complete(self) -> None:
        if self.task_id is None:
            return
        self.save()
        self.controller.toggle_task(self.task_id)

    def _delete(self) -> None:
        if self.task_id is None:
            return
        self.controller.delete_task(self.task_id)

    # -------------------------------------------------- 保存 / 取消

    def _on_save_clicked(self) -> None:
        if self.save() and self.task_id is not None:
            self._refresh_hints(self.db.get_task(self.task_id))

    def _cancel(self) -> None:
        self.cancel()

    def cancel(self) -> None:
        """丢弃本次改动并关闭面板。"""
        self.manual_edit.blockSignals(True)
        self.manual_edit.clear()
        self.manual_edit.blockSignals(False)
        if self.task_id is not None:
            self.load(self.task_id, discard=True)
        self.controller.close_detail(force=True)

    def save(self) -> bool:
        if self._loading or self.task_id is None or self._snapshot is None:
            return False
        task = self.db.get_task(self.task_id)
        if task is None:
            return False

        if self.repeat_combo.currentData() and not self._has_date:
            self._on_repeat_changed(self.repeat_combo.currentIndex())

        current = self._current_values()
        if current == self._snapshot:
            self._update_dirty_ui()
            return False

        title = current["title"] or task["title"]
        list_id = current["list_id"] or task["list_id"]
        self.db.update_task(
            self.task_id,
            title=title,
            notes=current["notes"],
            due_date=current["due_date"],
            due_time=current["due_time"],
            remind_offset=current["remind_offset"],
            priority=current["priority"],
            list_id=list_id,
            repeat_rule=current["repeat_rule"],
        )
        self._snapshot = self._task_values(self.db.get_task(self.task_id))
        self._refresh_hints(self.db.get_task(self.task_id))
        self.status_label.setText("已保存")
        self.status_label.setStyleSheet(f"color:{theme.SUCCESS};")
        self._update_dirty_ui()
        self.controller.on_task_changed(self.task_id)
        return True
