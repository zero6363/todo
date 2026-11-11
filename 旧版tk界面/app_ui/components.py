"""可复用控件：侧边栏条目、任务行。"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Iterable

import customtkinter as ctk

from .. import config, icon, utils
from . import theme

_CHECK_IMAGES: dict[tuple[str, int], "ctk.CTkImage"] = {}


def check_image(state: str, size: int = 20) -> "ctk.CTkImage":
    key = (state, size)
    cached = _CHECK_IMAGES.get(key)
    if cached is None:
        picture = icon.check_circle(size, state)
        cached = ctk.CTkImage(light_image=picture, dark_image=picture, size=(size, size))
        _CHECK_IMAGES[key] = cached
    return cached


def iter_widgets(widget: tk.Misc) -> Iterable[tk.Misc]:
    for child in widget.winfo_children():
        yield child
        yield from iter_widgets(child)


def bind_tree(widget: tk.Misc, sequence: str, handler, exclude: tuple = ()) -> None:
    for target in (widget, *iter_widgets(widget)):
        if any(target is item for item in exclude):
            continue
        target.bind(sequence, handler, add="+")


class Hoverable(ctk.CTkFrame):
    """鼠标悬停/选中变色的基础容器。"""

    def __init__(
        self,
        master,
        base_color: str = config.BG,
        hover_color: str = config.HOVER,
        selected_color: str = config.SELECTED,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", base_color)
        super().__init__(master, **kwargs)
        self.base_color = base_color
        self.hover_color = hover_color
        self.selected_color = selected_color
        self._hovering = False
        self._selected = False

    # -------------------------------------------------- 状态

    @property
    def current_color(self) -> str:
        if self._selected:
            return self.selected_color
        if self._hovering:
            return self.hover_color
        return self.base_color

    def _refresh_color(self) -> None:
        self.configure(fg_color=self.current_color)
        self.on_color_changed(self.current_color)

    def on_color_changed(self, color: str) -> None:
        """子类可覆盖，用于同步原生画布背景。"""

    def set_selected(self, value: bool) -> None:
        if self._selected != value:
            self._selected = value
            self._refresh_color()

    # -------------------------------------------------- 事件

    def bind_hover(self, exclude: tuple = ()) -> None:
        bind_tree(self, "<Enter>", self._on_enter, exclude=exclude)
        bind_tree(self, "<Leave>", self._on_leave, exclude=exclude)

    def _on_enter(self, _event=None) -> None:
        if not self._hovering:
            self._hovering = True
            self._refresh_color()

    def _on_leave(self, _event=None) -> None:
        self.after(20, self._check_pointer)

    def _check_pointer(self) -> None:
        try:
            under = self.winfo_containing(*self.winfo_pointerxy())
        except Exception:
            under = None
        inside = under is not None and str(under).startswith(str(self))
        if not inside and self._hovering:
            self._hovering = False
            self._refresh_color()


class SideBarItem(Hoverable):
    """侧边栏一行：色点 / 名称 / 数量。"""

    def __init__(
        self,
        master,
        text: str,
        count: int = 0,
        color: str | None = None,
        command: Callable[[], None] | None = None,
        on_menu: Callable | None = None,
    ):
        super().__init__(
            master,
            base_color=config.SIDEBAR_BG,
            hover_color=config.HOVER,
            selected_color=config.SELECTED,
            height=32,
            corner_radius=8,
        )
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)
        self._command = command
        self._on_menu = on_menu

        column = 0
        if color is not None:
            self.dot = ctk.CTkFrame(self, width=8, height=8, corner_radius=4, fg_color=color)
            self.dot.grid(row=0, column=0, padx=(11, 0), pady=12)
            column = 1
            left_pad = (9, 0)
        else:
            self.dot = None
            left_pad = (14, 0)

        self.label = ctk.CTkLabel(
            self,
            text=text,
            anchor="w",
            font=theme.font(13),
            text_color=config.TEXT,
        )
        self.label.grid(row=0, column=column, sticky="ew", padx=left_pad)

        self.badge = ctk.CTkLabel(
            self,
            text=str(count) if count else "",
            width=30,
            anchor="e",
            font=theme.font(11),
            text_color=config.TEXT_MUTED,
        )
        self.badge.grid(row=0, column=column + 1, padx=(0, 8))

        self.bind_hover()
        bind_tree(self, "<Button-1>", self._clicked)
        if on_menu is not None:
            bind_tree(self, "<Button-3>", self._right_clicked)

    def _clicked(self, _event=None) -> None:
        if self._command:
            self._command()

    def _right_clicked(self, event) -> None:
        if self._on_menu:
            self._on_menu(event)

    def set_count(self, count: int) -> None:
        self.badge.configure(text=str(count) if count else "")

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)

    def set_color(self, color: str) -> None:
        if self.dot is not None:
            self.dot.configure(fg_color=color)

    def refresh_style(self) -> None:
        accent = self._selected
        self.label.configure(
            text_color=config.ACCENT if accent else config.TEXT,
            font=theme.font(13, "bold") if accent else theme.font(13),
        )
        self.badge.configure(text_color=config.ACCENT if accent else config.TEXT_MUTED)

    def set_selected(self, value: bool) -> None:
        super().set_selected(value)
        self.refresh_style()


class SegmentedControl(ctk.CTkFrame):
    """自绘分段选择器：选中项白字蓝底，未选中灰字浅底。"""

    def __init__(
        self,
        master,
        values: list[str],
        command: Callable[[str], None] | None = None,
        height: int = 30,
        font_size: int = 12,
    ):
        super().__init__(master, fg_color="#EEF1F5", corner_radius=8, height=height)
        self._values = list(values)
        self._command = command
        self._value = self._values[0] if self._values else ""
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._font_size = font_size
        self.grid_propagate(False)

        for index, value in enumerate(self._values):
            self.grid_columnconfigure(index, weight=1)
            button = ctk.CTkButton(
                self,
                text=value,
                height=max(height - 6, 20),
                corner_radius=6,
                font=theme.font(font_size),
                fg_color="transparent",
                hover_color="#E2E7EE",
                text_color=config.TEXT_SUB,
                command=lambda v=value: self.set(v, notify=True),
            )
            pad_left = 3 if index == 0 else 1
            pad_right = 3 if index == len(self._values) - 1 else 1
            button.grid(row=0, column=index, padx=(pad_left, pad_right), pady=3, sticky="ew")
            self._buttons[value] = button

        self._paint()

    def _paint(self) -> None:
        for value, button in self._buttons.items():
            selected = value == self._value
            button.configure(
                fg_color=config.ACCENT if selected else "transparent",
                hover_color=config.ACCENT_HOVER if selected else "#E2E7EE",
                text_color="#FFFFFF" if selected else config.TEXT_SUB,
                font=theme.font(self._font_size, "bold") if selected else theme.font(self._font_size),
            )

    def set(self, value: str, notify: bool = False) -> None:
        if value not in self._buttons:
            return
        changed = value != self._value
        self._value = value
        self._paint()
        if notify and changed and self._command:
            self._command(value)

    def get(self) -> str:
        return self._value


class TaskRow(Hoverable):
    """任务列表中的一行。"""

    def __init__(
        self,
        master,
        task,
        on_toggle: Callable[[int], None],
        on_open: Callable[[int], None],
        on_menu: Callable[[int, tk.Event], None],
    ):
        super().__init__(
            master,
            base_color=config.BG,
            hover_color=config.HOVER,
            selected_color=config.SELECTED,
            height=56,
            corner_radius=8,
        )
        self.grid_propagate(False)
        self.grid_columnconfigure(2, weight=1)
        self.task = task
        self.task_id = int(task["id"])
        self._completed = bool(task["completed"])
        self._on_toggle = on_toggle
        self._on_open = on_open
        self._on_menu = on_menu

        # 优先级色条
        priority = int(task["priority"] or 0)
        bar_color = config.PRIORITY_COLORS.get(priority) or self.base_color
        self.bar = ctk.CTkFrame(self, width=3, height=26, corner_radius=2, fg_color=bar_color)
        self.bar.grid(row=0, column=0, padx=(7, 0), pady=15, sticky="ns")

        # 勾选框
        self.chk = ctk.CTkLabel(
            self,
            text="",
            width=20,
            height=20,
            image=check_image("done" if self._completed else "normal"),
            cursor="hand2",
        )
        self.chk.grid(row=0, column=1, padx=(10, 8), pady=18)
        self.chk.bind("<Button-1>", self._toggle)
        self.chk.bind("<Enter>", self._circle_enter)
        self.chk.bind("<Leave>", self._circle_leave)

        # 文本
        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.grid(row=0, column=2, sticky="ew", pady=(10, 9))
        text_frame.grid_columnconfigure(0, weight=1)

        title_font = theme.font(13, overstrike=True) if self._completed else theme.font(13)
        title_color = config.TEXT_MUTED if self._completed else config.TEXT
        self.title = ctk.CTkLabel(
            text_frame,
            text=utils.truncate(task["title"], 60),
            anchor="w",
            justify="left",
            font=title_font,
            text_color=title_color,
        )
        self.title.grid(row=0, column=0, sticky="w")

        meta_parts = []
        if task["list_name"]:
            meta_parts.append(task["list_name"])
        notes = (task["notes"] or "").strip()
        if notes:
            meta_parts.append("有备注")
        if int(task["defer_count"] or 0) > 0:
            meta_parts.append(f"已延期 {int(task['defer_count'])} 次")
        self.meta = ctk.CTkLabel(
            text_frame,
            text=" · ".join(meta_parts),
            anchor="w",
            font=theme.font(11),
            text_color=config.TEXT_MUTED,
            height=16,
        )
        if meta_parts:
            self.meta.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # 日期标签
        due_text, chip_bg, chip_fg = self._due_chip(task)
        self.chip = ctk.CTkLabel(
            self,
            text=due_text,
            font=theme.font(11),
            text_color=chip_fg,
            fg_color=chip_bg if chip_bg else "transparent",
            corner_radius=5,
            height=20,
            width=0,
        )
        if due_text:
            self.chip.grid(row=0, column=3, padx=(6, 12), pady=18, sticky="e")

        self.bind_hover(exclude=(self.chk,))
        bind_tree(self, "<Button-1>", self._open, exclude=(self.chk,))
        bind_tree(self, "<Button-3>", self._menu, exclude=(self.chk,))
        self.chk.bind("<Button-3>", self._menu, add="+")
        self.bind("<Double-Button-1>", self._open, add="+")

    # -------------------------------------------------- 外观

    @staticmethod
    def _due_chip(task) -> tuple[str, str, str]:
        due_date = task["due_date"]
        if not due_date:
            return "", "", config.TEXT_MUTED
        text = utils.describe_due(due_date, task["due_time"])
        if task["completed"]:
            return text, "", config.TEXT_MUTED
        if utils.is_overdue(due_date, task["due_time"]):
            return text, config.DANGER_SOFT, config.DANGER
        if due_date == utils.today().isoformat():
            return text, config.ACCENT_SOFT, config.ACCENT
        return text, "", config.TEXT_MUTED

    def on_color_changed(self, color: str) -> None:
        if int(self.task["priority"] or 0) == 0:
            self.bar.configure(fg_color=color)

    def _circle_enter(self, _event=None) -> None:
        if not self._completed:
            self.chk.configure(image=check_image("hover"))

    def _circle_leave(self, _event=None) -> None:
        if not self._completed:
            self.chk.configure(image=check_image("normal"))

    # -------------------------------------------------- 事件

    def _toggle(self, _event=None) -> None:
        self._on_toggle(self.task_id)

    def _open(self, _event=None) -> None:
        self._on_open(self.task_id)

    def _menu(self, event) -> None:
        self._on_menu(self.task_id, event)
