"""任务列表页：标题、搜索、快速添加、任务行。"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    CheckBox,
    FluentIcon as FIF,
    LineEdit,
    PrimaryPushButton,
    RoundMenu,
    SearchLineEdit,
    SmoothScrollArea,
    TitleLabel,
    TransparentToolButton,
    Action,
)

from .. import config, utils
from . import theme
from .widgets import EmptyState, TaskRow

QUICK_ADD_PLACEHOLDER = "添加任务，试试「明天十点」「1小时后」「每天10点」"
QUICK_ADD_HINT = "回车添加 · 支持「十点半」「1小时后」「下周一 上午十点」「每天10点」「每三天十点」；不写时间默认今天 14:00"


class TaskPage(QWidget):
    def __init__(self, controller, view_type: str, view_id: int | None = None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.view_type = view_type
        self.view_id = view_id
        self.rows: list[TaskRow] = []
        self.setObjectName(f"list_{view_id}" if view_type == "list" else f"page_{view_type}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 16, 22, 8)
        layout.setSpacing(8)

        # 标题行
        header = QHBoxLayout()
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title_label = TitleLabel("今天")
        self.subtitle_label = CaptionLabel("")
        self.subtitle_label.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        header.addLayout(titles, 1)

        self.search = SearchLineEdit()
        self.search.setPlaceholderText("搜索任务")
        self.search.setFixedWidth(190)
        self.search.textChanged.connect(lambda _: self.refresh())
        header.addWidget(self.search, 0, Qt.AlignVCenter)

        self.show_completed = CheckBox("显示已完成")
        self.show_completed.setChecked(False)
        self.show_completed.checkStateChanged.connect(lambda _: self.refresh())
        if view_type != "completed":
            header.addWidget(self.show_completed, 0, Qt.AlignVCenter)

        self.more_button = TransparentToolButton(FIF.MORE)
        self.more_button.setFixedSize(32, 32)
        self.more_button.clicked.connect(self._show_list_menu)
        if view_type == "list":
            header.addWidget(self.more_button, 0, Qt.AlignVCenter)

        layout.addLayout(header)

        # 快速添加
        self.add_row = QWidget(self)
        add_layout = QHBoxLayout(self.add_row)
        add_layout.setContentsMargins(0, 6, 0, 0)
        add_layout.setSpacing(8)
        self.input = LineEdit()
        self.input.setPlaceholderText(QUICK_ADD_PLACEHOLDER)
        self.input.setClearButtonEnabled(True)
        self.input.setMinimumHeight(38)
        self.input.returnPressed.connect(self._on_add)
        self.input.textChanged.connect(self._on_text_changed)
        add_layout.addWidget(self.input, 1)
        self.add_button = PrimaryPushButton("添加")
        self.add_button.setFixedWidth(76)
        self.add_button.setMinimumHeight(38)
        self.add_button.clicked.connect(self._on_add)
        add_layout.addWidget(self.add_button)
        layout.addWidget(self.add_row)

        # 识别结果胶囊：像「📅 今天 · 22:00」「🔁 每天」直接挂在输入框下面
        self.chip_row = QWidget(self)
        chip_layout = QHBoxLayout(self.chip_row)
        chip_layout.setContentsMargins(4, 4, 0, 0)
        chip_layout.setSpacing(6)
        layout.addWidget(self.chip_row)
        self.chip_row.hide()

        self.hint_label = CaptionLabel(QUICK_ADD_HINT)
        self.hint_label.setTextFormat(Qt.RichText)
        self.hint_label.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        layout.addWidget(self.hint_label)

        if view_type == "completed":
            self.add_row.hide()
            self.chip_row.hide()
            self.hint_label.hide()

        # 列表
        self.scroll = SmoothScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(theme.SCROLL_QSS)
        self.body = QWidget()
        self.body.setStyleSheet("background: transparent;")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 6, 6, 8)
        self.body_layout.setSpacing(2)
        self.body_layout.addStretch(1)
        self.scroll.setWidget(self.body)
        layout.addWidget(self.scroll, 1)

        self._text_cache = ""

    # -------------------------------------------------- 刷新

    def search_text(self) -> str:
        return self.search.text().strip()

    def refresh(self) -> None:
        self._clear_rows()
        rows = self.controller.query_tasks(
            self.view_type, self.view_id, self.show_completed.isChecked(), self.search_text()
        )
        if not rows:
            self._add_widget(self._empty_state())
        else:
            for task in rows:
                row = TaskRow(task, self.body)
                row.toggled.connect(self.controller.toggle_task)
                row.opened.connect(self.controller.open_task)
                row.menu_requested.connect(self.controller.task_menu)
                self._add_widget(row)
                self.rows.append(row)
        self._update_header(len(rows))
        self.highlight(self.controller.current_task_id)

    def _add_widget(self, widget: QWidget) -> None:
        self.body_layout.insertWidget(self.body_layout.count() - 1, widget)

    def _clear_rows(self) -> None:
        self.rows.clear()
        while self.body_layout.count() > 1:
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _empty_state(self) -> QWidget:
        if self.search_text():
            return EmptyState("没有找到匹配的任务", "换个关键词试试", parent=self.body)
        mapping = {
            "today": ("今天没有安排", "享受空白，或在上方输入框添加一个新任务"),
            "next7": ("最近 7 天没有任务", "把要紧的事安排进来吧"),
            "all": ("这里还没有任务", "在上方输入框敲下第一件事"),
            "inbox": ("收集箱是空的", "没有截止日期的任务都会待在这里"),
            "list": ("这个清单还是空的", "添加第一个任务"),
            "completed": ("还没有完成的任务", "完成任务后会出现在这里"),
        }
        title, hint = mapping.get(self.view_type, ("这里还没有任务", "添加一个新任务"))
        return EmptyState(
            title,
            hint,
            "新建任务" if self.view_type != "completed" else "",
            self.focus_input,
            self.body,
        )

    def _update_header(self, shown: int) -> None:
        title, subtitle = self.controller.header_text(
            self.view_type, self.view_id, shown, bool(self.search_text())
        )
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)

    def highlight(self, task_id: int | None) -> None:
        for row in self.rows:
            row.set_selected(row.task_id == task_id)

    # -------------------------------------------------- 交互

    def _on_add(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.controller.quick_add(text, self)
        self.input.clear()
        self.input.setFocus()

    def _on_text_changed(self, text: str) -> None:
        if text == self._text_cache:
            return
        self._text_cache = text
        self._update_chips(utils.parse_quick_input(text), text)

    def _update_chips(self, parsed: dict, text: str = "") -> None:
        """识别到日期/循环/优先级时，在输入框下面显示彩色胶囊。"""
        chips = []
        if parsed.get("matched"):
            label = parsed["matched"]
            if parsed.get("due_date") and not parsed.get("due_time"):
                # 只识别出日期：默认时间也一起显示出来
                label = f"{label} {config.DEFAULT_DUE_CLOCK}"
            chips.append((f"📅 {label}", theme.ACCENT, "#E8EFFD"))
        elif text.strip():
            # 只写了任务名：默认今天 14:00
            chips.append(
                (f"📅 今天 {config.DEFAULT_DUE_CLOCK}（默认）", theme.TEXT_MUTED, "#F1F2F4")
            )
        if parsed.get("repeat_label"):
            chips.append((f"🔁 {parsed['repeat_label']}", theme.REPEAT, "#F0EAFD"))
        if parsed.get("priority"):
            level = int(parsed["priority"])
            name = config.PRIORITY_NAMES.get(level, "")
            color = theme.DANGER if level >= 3 else theme.WARN
            bg = "#FCEAEA" if level >= 3 else "#FDF3E3"
            chips.append((f"❗ {name}优先级", color, bg))

        # 清空旧胶囊（deleteLater 是异步的，先隐藏脱离布局，避免和新胶囊叠影）
        while self.chip_row.layout().count():
            item = self.chip_row.layout().takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        if not chips:
            self.chip_row.hide()
            self.hint_label.setText(QUICK_ADD_HINT)
            return

        for text, color, bg in chips:
            chip = QLabel(self.chip_row)
            chip.setTextFormat(Qt.RichText)
            chip.setText(escape(text))
            chip.setStyleSheet(
                f"background:{bg};color:{color};font-weight:600;"
                "border-radius:11px;padding:3px 12px;"
            )
            self.chip_row.layout().addWidget(chip)
        tail = QLabel(self.chip_row)
        tail.setTextFormat(Qt.RichText)
        tail.setText(f"<span style='color:{theme.TEXT_MUTED}'>回车添加</span>")
        self.chip_row.layout().addWidget(tail)
        self.chip_row.layout().addStretch(1)
        self.chip_row.show()
        self.hint_label.setText("")

    def focus_input(self) -> None:
        self.add_row.show()
        self.input.setFocus()

    def _show_list_menu(self) -> None:
        if self.view_type != "list" or self.view_id is None:
            return
        menu = RoundMenu(parent=self)
        rename = Action(
            icon=FIF.EDIT,
            text="重命名 / 改颜色",
            triggered=lambda: self.controller.edit_list(self.view_id),
        )
        delete = Action(
            icon=FIF.DELETE,
            text="删除清单",
            triggered=lambda: self.controller.delete_list(self.view_id),
        )
        menu.addAction(rename)
        menu.addAction(delete)
        menu.exec(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))
