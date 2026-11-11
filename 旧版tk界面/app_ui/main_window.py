"""主窗口：侧边栏 + 任务列表 + 详情面板。"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from typing import Callable

import customtkinter as ctk

from .. import autostart, config, utils
from ..db import parse_due_date, parse_due_time
from ..icon import make_icon
from ..notifier import Notifier
from ..reminder import ReminderService
from ..sound import play_alert as sound_alert
from ..tray import TrayIcon
from . import dialogs, theme
from .components import SegmentedControl, SideBarItem, TaskRow
from .reminder_popup import ReminderPopup

log = logging.getLogger("lighttodo")

NAV_ITEMS = [
    ("today", "今天"),
    ("next7", "最近 7 天"),
    ("all", "全部"),
    ("inbox", "收集箱"),
    ("completed", "已完成"),
]


class MainWindow(ctk.CTk):
    def __init__(self, db, notifier: Notifier, start_minimized: bool = False):
        super().__init__()
        self.db = db
        self.notifier = notifier
        self.start_minimized = start_minimized

        self._queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._view: dict = {"type": "today", "id": None}
        self._search = ""
        self._show_completed = False
        self._current_task_id: int | None = None
        self._list_widgets: list[tk.Misc] = []
        self._nav_items: dict[str, SideBarItem] = {}
        self._list_items: dict[int, SideBarItem] = {}
        self._popups: list[ReminderPopup] = []
        self._loading_detail = False
        self._save_job: str | None = None
        self._list_map: dict[str, int] = {}
        self._running = True

        self._setup_window()
        self._build_sidebar()
        self._build_main()
        self._build_detail()
        self._bind_shortcuts()

        self.reminder = ReminderService(self.db, self.notifier, self.post)
        self.reminder.on_reminder = self.show_reminder_popup
        self.reminder.on_day_change = self._on_day_change

        self.tray = TrayIcon(make_icon(64), self.post)
        self._wire_tray()

        self.notifier.set_fallback(self.tray.notify)

        self.refresh_nav()
        self.refresh_tasks()
        self._restore_geometry()

        self.tray.start()
        self.reminder.start()
        self.after(120, self._pump)

        if self.start_minimized:
            self.withdraw()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(400, self._apply_initial_settings)

    # ================================================== 基础

    def _setup_window(self) -> None:
        self.title(config.APP_NAME)
        self.geometry("1180x760")
        self.minsize(980, 620)
        self.configure(fg_color=config.BG)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        try:
            icon = config.data_dir() / "icon.ico"
            if icon.exists():
                self.iconbitmap(str(icon))
        except Exception:
            pass
        self._center_window(1180, 760)

    def _center_window(self, width: int, height: int) -> None:
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max((sw - width) // 2, 0)
            y = max((sh - height) // 2 - 20, 0)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass

    def _restore_geometry(self) -> None:
        saved = self.db.get_setting("window_geometry", "")
        if saved:
            try:
                self.geometry(saved)
            except Exception:
                pass

    def _save_geometry(self) -> None:
        try:
            if self.state() == "normal":
                self.db.set_setting("window_geometry", self.geometry())
        except Exception:
            pass

    # ================================================== 侧边栏

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=238, corner_radius=0, fg_color=config.SIDEBAR_BG)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(5, weight=1)
        self.sidebar = side

        # 品牌
        brand = ctk.CTkFrame(side, fg_color="transparent", height=52)
        brand.grid(row=0, column=0, sticky="ew", padx=14, pady=(16, 6))
        brand.grid_propagate(False)
        logo = ctk.CTkImage(light_image=make_icon(64), dark_image=make_icon(64), size=(28, 28))
        ctk.CTkLabel(brand, image=logo, text="").pack(side="left")
        ctk.CTkLabel(
            brand, text=config.APP_NAME, font=theme.font(16, "bold"), text_color=config.TEXT
        ).pack(side="left", padx=(9, 0))

        # 搜索
        self.search_entry = ctk.CTkEntry(
            side,
            placeholder_text="搜索任务",
            height=32,
            corner_radius=8,
            border_width=1,
            border_color=config.BORDER,
            fg_color="#FFFFFF",
            font=theme.font(12),
            text_color=config.TEXT,
            placeholder_text_color=config.TEXT_MUTED,
        )
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 10))
        self.search_entry.bind("<KeyRelease>", self._on_search_key)

        # 导航
        nav = ctk.CTkFrame(side, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="ew", padx=8)
        for key, label in NAV_ITEMS:
            item = SideBarItem(nav, label, command=lambda k=key: self.select_view(k))
            item.pack(fill="x", pady=1)
            self._nav_items[key] = item

        # 清单标题
        header = ctk.CTkFrame(side, fg_color="transparent", height=30)
        header.grid(row=3, column=0, sticky="ew", padx=(20, 12), pady=(14, 2))
        ctk.CTkLabel(
            header, text="我的清单", font=theme.font(11, "bold"), text_color=config.TEXT_MUTED
        ).pack(side="left")
        ctk.CTkButton(
            header,
            text="+",
            width=22,
            height=22,
            corner_radius=6,
            font=theme.font(14),
            fg_color="transparent",
            hover_color=config.HOVER,
            text_color=config.TEXT_SUB,
            command=self.new_list,
        ).pack(side="right")

        # 清单滚动区
        self.lists_frame = ctk.CTkScrollableFrame(
            side,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color="#DDE1E7",
            scrollbar_button_hover_color="#C7CDD6",
        )
        self.lists_frame.grid(row=5, column=0, sticky="nsew", padx=(8, 4), pady=(0, 6))

        # 底部
        footer = ctk.CTkFrame(side, fg_color="transparent")
        footer.grid(row=6, column=0, sticky="ew", padx=8, pady=(2, 12))
        self.settings_item = SideBarItem(footer, "设置", command=self.open_settings)
        self.settings_item.pack(fill="x")

    # ================================================== 主区域

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, corner_radius=0, fg_color=config.BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)
        self.main = main

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 2))
        header.grid_columnconfigure(0, weight=1)

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w")
        self.view_title = ctk.CTkLabel(
            titles, text="今天", anchor="w", font=theme.font(21, "bold"), text_color=config.TEXT
        )
        self.view_title.pack(anchor="w")
        self.view_sub = ctk.CTkLabel(
            titles, text="", anchor="w", font=theme.font(11), text_color=config.TEXT_MUTED
        )
        self.view_sub.pack(anchor="w", pady=(2, 0))

        self.completed_check = ctk.CTkCheckBox(
            header,
            text="显示已完成",
            font=theme.font(11),
            text_color=config.TEXT_SUB,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4,
            fg_color=config.ACCENT,
            hover_color=config.ACCENT_HOVER,
            border_color=config.BORDER,
            command=self._toggle_show_completed,
        )
        self.completed_check.grid(row=0, column=1, sticky="e", padx=(12, 0), pady=(6, 0))

        # 快速添加
        add_bar = ctk.CTkFrame(
            main,
            fg_color=config.PANEL_BG,
            corner_radius=10,
            border_width=1,
            border_color=config.BORDER,
        )
        add_bar.grid(row=1, column=0, sticky="ew", padx=24, pady=(12, 10))
        add_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            add_bar, text="+", font=theme.font(16), text_color=config.ACCENT, width=20
        ).grid(row=0, column=0, sticky="w", padx=(14, 0))
        self.add_entry = ctk.CTkEntry(
            add_bar,
            placeholder_text="添加任务，支持「明天 18:00」这样的写法",
            height=40,
            corner_radius=0,
            border_width=0,
            fg_color="transparent",
            font=theme.font(13),
            text_color=config.TEXT,
            placeholder_text_color=config.TEXT_MUTED,
        )
        self.add_entry.grid(row=0, column=1, sticky="ew", padx=(4, 6))
        self.add_entry.bind("<Return>", self._on_quick_add)
        ctk.CTkButton(
            add_bar,
            text="添加",
            width=64,
            height=30,
            corner_radius=7,
            font=theme.font(12),
            fg_color=config.ACCENT,
            hover_color=config.ACCENT_HOVER,
            command=lambda: self._on_quick_add(None),
        ).grid(row=0, column=2, padx=(0, 10))

        # 任务列表
        self.list_frame = ctk.CTkScrollableFrame(
            main,
            fg_color=config.BG,
            corner_radius=0,
            scrollbar_button_color="#E2E6EC",
            scrollbar_button_hover_color="#CBD2DB",
        )
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=(14, 6), pady=(0, 10))
        try:
            self.list_frame._parent_canvas.configure(bg=config.BG)
        except Exception:
            pass

    # ================================================== 详情面板

    def _build_detail(self) -> None:
        panel = ctk.CTkFrame(
            self,
            width=352,
            corner_radius=0,
            fg_color=config.PANEL_BG,
            border_width=1,
            border_color=config.BORDER,
        )
        panel.grid(row=0, column=2, sticky="nse")
        panel.grid_propagate(False)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        self.detail = panel

        head = ctk.CTkFrame(panel, fg_color="transparent", height=48)
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 0))
        ctk.CTkLabel(
            head, text="任务详情", font=theme.font(13, "bold"), text_color=config.TEXT
        ).pack(side="left")
        ctk.CTkButton(
            head,
            text="×",
            width=26,
            height=26,
            corner_radius=6,
            font=theme.font(15),
            fg_color="transparent",
            hover_color=config.HOVER,
            text_color=config.TEXT_MUTED,
            command=self.close_detail,
        ).pack(side="right")

        body = ctk.CTkScrollableFrame(
            panel,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color="#E2E6EC",
            scrollbar_button_hover_color="#CBD2DB",
        )
        body.grid(row=1, column=0, sticky="nsew", padx=(14, 6), pady=(0, 10))
        body.grid_columnconfigure(0, weight=1)
        self.detail_body = body

        # 标题
        self.d_title = ctk.CTkTextbox(
            body,
            height=56,
            fg_color="transparent",
            border_width=0,
            font=theme.font(15, "bold"),
            text_color=config.TEXT,
            wrap="word",
            activate_scrollbars=False,
        )
        self.d_title.grid(row=0, column=0, sticky="ew", pady=(2, 8))
        self.d_title.bind("<KeyRelease>", lambda e: self._schedule_save())
        self.d_title.bind("<Return>", lambda e: "break")

        self._detail_field(body, 1, "清单", self._make_list_menu)
        self._detail_field(body, 2, "截止日期", self._make_date_row)
        self._detail_field(body, 3, "时间", self._make_time_row)
        self._detail_field(body, 4, "提醒", self._make_remind_menu)
        self._detail_field(body, 5, "优先级", self._make_priority_row)

        ctk.CTkLabel(
            body, text="备注", anchor="w", font=theme.font(11, "bold"), text_color=config.TEXT_MUTED
        ).grid(row=6, column=0, sticky="w", pady=(10, 4))
        self.d_notes = ctk.CTkTextbox(
            body,
            height=112,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=config.BORDER,
            corner_radius=8,
            font=theme.font(12),
            text_color=config.TEXT,
            wrap="word",
        )
        self.d_notes.grid(row=7, column=0, sticky="ew")
        self.d_notes.bind("<KeyRelease>", lambda e: self._schedule_save())

        self.d_info = ctk.CTkLabel(
            body, text="", anchor="w", justify="left", font=theme.font(11), text_color=config.TEXT_MUTED
        )
        self.d_info.grid(row=8, column=0, sticky="w", pady=(12, 6))

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=9, column=0, sticky="ew", pady=(2, 12))
        ctk.CTkButton(
            actions,
            text="标记完成",
            width=96,
            height=32,
            corner_radius=8,
            font=theme.font(12),
            fg_color=config.ACCENT_SOFT,
            hover_color="#DBE6FF",
            text_color=config.ACCENT,
            command=self._complete_current,
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="删除任务",
            width=88,
            height=32,
            corner_radius=8,
            font=theme.font(12),
            fg_color="transparent",
            hover_color=config.DANGER_SOFT,
            text_color=config.DANGER,
            border_width=1,
            border_color=config.BORDER,
            command=self._delete_current,
        ).pack(side="right")

        panel.grid_remove()

    def _detail_field(self, parent, row: int, label: str, factory) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        block.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            block, text=label, anchor="w", font=theme.font(11, "bold"), text_color=config.TEXT_MUTED
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        holder = ctk.CTkFrame(block, fg_color="transparent")
        holder.grid(row=1, column=0, sticky="ew")
        factory(holder)

    # --- 详情控件工厂 -------------------------------------------------

    def _make_list_menu(self, parent) -> None:
        self.d_list = ctk.CTkOptionMenu(
            parent,
            values=["收集箱"],
            height=32,
            corner_radius=8,
            font=theme.font(12),
            fg_color="#F2F4F7",
            button_color="#F2F4F7",
            button_hover_color="#E6EAF0",
            text_color=config.TEXT,
            dropdown_fg_color="#FFFFFF",
            dropdown_text_color=config.TEXT,
            dropdown_hover_color=config.HOVER,
            dropdown_font=theme.font(12),
            command=self._on_detail_list,
        )
        self.d_list.pack(fill="x")

    def _make_date_row(self, parent) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        self.d_date = ctk.CTkEntry(
            row,
            height=32,
            corner_radius=8,
            font=theme.font(12),
            fg_color="#FFFFFF",
            border_color=config.BORDER,
            placeholder_text="YYYY-MM-DD",
            text_color=config.TEXT,
        )
        self.d_date.pack(side="left", fill="x", expand=True)
        self.d_date.bind("<KeyRelease>", lambda e: self._schedule_save())
        self.d_date.bind("<FocusOut>", lambda e: self._save_detail())
        for label, delta in (("今天", 0), ("明天", 1)):
            ctk.CTkButton(
                row,
                text=label,
                width=44,
                height=28,
                corner_radius=6,
                font=theme.font(11),
                fg_color="transparent",
                hover_color=config.HOVER,
                text_color=config.TEXT_SUB,
                border_width=1,
                border_color=config.BORDER,
                command=lambda d=delta: self._quick_date(d),
            ).pack(side="left", padx=(6, 0))
        ctk.CTkButton(
            row,
            text="清除",
            width=44,
            height=28,
            corner_radius=6,
            font=theme.font(11),
            fg_color="transparent",
            hover_color=config.HOVER,
            text_color=config.TEXT_MUTED,
            command=self._clear_date,
        ).pack(side="left", padx=(4, 0))

    def _make_time_row(self, parent) -> None:
        self.d_time = ctk.CTkEntry(
            parent,
            height=32,
            corner_radius=8,
            font=theme.font(12),
            fg_color="#FFFFFF",
            border_color=config.BORDER,
            placeholder_text="HH:MM，留空表示全天",
            text_color=config.TEXT,
        )
        self.d_time.pack(fill="x")
        self.d_time.bind("<KeyRelease>", lambda e: self._schedule_save())
        self.d_time.bind("<FocusOut>", lambda e: self._save_detail())

    def _make_remind_menu(self, parent) -> None:
        self.d_remind = ctk.CTkOptionMenu(
            parent,
            values=config.REMIND_LABELS,
            height=32,
            corner_radius=8,
            font=theme.font(12),
            fg_color="#F2F4F7",
            button_color="#F2F4F7",
            button_hover_color="#E6EAF0",
            text_color=config.TEXT,
            dropdown_fg_color="#FFFFFF",
            dropdown_text_color=config.TEXT,
            dropdown_hover_color=config.HOVER,
            dropdown_font=theme.font(12),
            command=lambda v: self._schedule_save(immediate=True),
        )
        self.d_remind.pack(fill="x")

    def _make_priority_row(self, parent) -> None:
        self.d_priority = SegmentedControl(
            parent,
            values=["无", "低", "中", "高"],
            height=30,
            command=lambda v: self._schedule_save(immediate=True),
        )
        self.d_priority.pack(fill="x")

    # ================================================== 快捷键

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-n>", lambda e: self.focus_add_entry())
        self.bind("<Control-f>", lambda e: self.focus_search())
        self.bind("<Control-comma>", lambda e: self.open_settings())
        self.bind("<Escape>", lambda e: self.close_detail())
        self.bind("<F5>", lambda e: self.refresh_tasks())

    # ================================================== 数据刷新

    def refresh_nav(self) -> None:
        counts = self.db.counts()
        for key in ("today", "next7", "all", "inbox", "completed"):
            item = self._nav_items.get(key)
            if item:
                item.set_count(counts.get(key, 0))

        for list_id, item in list(self._list_items.items()):
            item.set_count(counts["lists"].get(list_id, 0))

        self._rebuild_lists(counts)
        self._sync_selection()

        today_count = counts.get("today", 0)
        self.title(f"{config.APP_NAME} · 今天 {today_count} 项")
        if hasattr(self, "tray"):
            self.tray.set_today_count(today_count)

    def _rebuild_lists(self, counts: dict) -> None:
        existing = {int(row["id"]) for row in self.db.lists()}
        for list_id in list(self._list_items):
            if list_id not in existing:
                widget = self._list_items.pop(list_id)
                try:
                    widget.destroy()
                except Exception:
                    pass
        for row in self.db.lists():
            list_id = int(row["id"])
            item = self._list_items.get(list_id)
            if item is None:
                item = SideBarItem(
                    self.lists_frame,
                    row["name"],
                    count=counts["lists"].get(list_id, 0),
                    color=row["color"],
                    command=lambda i=list_id: self.select_view("list", i),
                    on_menu=lambda event, i=list_id: self._list_menu(event, i),
                )
                item.pack(fill="x", pady=1)
                self._list_items[list_id] = item
            else:
                item.set_text(row["name"])
                item.set_color(row["color"])
                item.set_count(counts["lists"].get(list_id, 0))

    def _on_search_key(self, _event=None) -> None:
        text = self.search_entry.get().strip()
        if text == self._search:
            return
        self._search = text
        self.refresh_tasks()

    def refresh_tasks(self, keep_scroll: bool = False) -> None:
        scroll = 0.0
        if keep_scroll:
            try:
                scroll = self.list_frame._parent_canvas.yview()[0]
            except Exception:
                scroll = 0.0

        for widget in self._list_widgets:
            try:
                widget.destroy()
            except Exception:
                pass
        self._list_widgets.clear()

        view_type = "search" if self._search else self._view["type"]
        rows = self.db.tasks_for_view(
            view_type,
            view_id=self._view.get("id"),
            search=self._search,
            show_completed=self._show_completed,
        )

        if not rows:
            self._show_empty_state()
        else:
            for task in rows:
                row = TaskRow(
                    self.list_frame,
                    task,
                    on_toggle=self.toggle_task,
                    on_open=self.open_task,
                    on_menu=self.task_menu,
                )
                row.pack(fill="x", pady=1)
                row.set_selected(self._current_task_id == int(task["id"]))
                self._list_widgets.append(row)

        self._update_header(len(rows))
        if keep_scroll:
            try:
                self.list_frame._parent_canvas.yview_moveto(scroll)
            except Exception:
                pass

    def _show_empty_state(self) -> None:
        wrap = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True, pady=(60, 0))
        title, hint = self._empty_texts()
        ctk.CTkLabel(
            wrap, text=title, font=theme.font(15, "bold"), text_color=config.TEXT_SUB
        ).pack()
        ctk.CTkLabel(
            wrap, text=hint, font=theme.font(11), text_color=config.TEXT_MUTED, justify="center"
        ).pack(pady=(6, 12))
        ctk.CTkButton(
            wrap,
            text="新建任务",
            width=96,
            height=32,
            corner_radius=8,
            font=theme.font(12),
            fg_color=config.ACCENT,
            hover_color=config.ACCENT_HOVER,
            command=self.focus_add_entry,
        ).pack()
        self._list_widgets.append(wrap)

    def _empty_texts(self) -> tuple[str, str]:
        if self._search:
            return "没有找到匹配的任务", f"换个关键词试试，或者清空搜索框"
        view_type = self._view["type"]
        if view_type == "today":
            return "今天没有安排", "享受空白，或在上方输入框添加一个新任务"
        if view_type == "completed":
            return "还没有完成的任务", "完成任务后会出现在这里"
        if view_type == "inbox":
            return "收集箱是空的", "没有日期的任务都会待在这里"
        return "这里还没有任务", "在上方输入框敲下第一件事吧"

    def _update_header(self, shown: int) -> None:
        if self._search:
            self.view_title.configure(text="搜索结果")
            self.view_sub.configure(text=f"「{self._search}」匹配到 {shown} 项")
            return
        counts = self.db.counts()
        view_type = self._view["type"]
        if view_type == "list" and self._view.get("id"):
            name = next(
                (row["name"] for row in self.db.lists() if int(row["id"]) == self._view["id"]), "清单"
            )
            self.view_title.configure(text=name)
        else:
            labels = dict(NAV_ITEMS)
            self.view_title.configure(text=labels.get(view_type, "任务"))
        if view_type == "completed":
            self.view_sub.configure(text=f"共 {shown} 项已完成")
        else:
            pending = counts.get(view_type, shown) if view_type != "list" else shown
            self.view_sub.configure(text=f"{pending} 项待完成")

    def select_view(self, view_type: str, list_id: int | None = None) -> None:
        self._flush_save()
        self._view = {"type": view_type, "id": list_id}
        if self._search:
            self._search = ""
            self.search_entry.delete(0, "end")
        self.close_detail(save=False)
        self._sync_selection()
        self.refresh_nav()
        self.refresh_tasks()

    def _sync_selection(self) -> None:
        view_type = self._view["type"]
        for key, item in self._nav_items.items():
            item.set_selected(key == view_type)
        for list_id, item in self._list_items.items():
            item.set_selected(view_type == "list" and list_id == self._view.get("id"))

    # ================================================== 增删改

    def _on_quick_add(self, _event=None) -> None:
        text = self.add_entry.get().strip()
        if not text:
            return
        parsed = utils.parse_quick_input(text)
        due_date = parsed["due_date"]
        due_time = parsed["due_time"]
        if due_time and not due_date:
            # 只写了时间：没到点就今天，已经过了就明天
            now = datetime.now()
            target = now.date() if due_time > now.strftime("%H:%M") else now.date() + timedelta(days=1)
            due_date = target.isoformat()
        if due_date is None and self._view["type"] == "today":
            due_date = date.today().isoformat()
        list_id = self._view["id"] if self._view["type"] == "list" else self.db.default_list_id()
        remind_offset = 0 if (due_date and due_time) else None
        self.db.add_task(
            parsed["title"],
            list_id=list_id,
            due_date=due_date,
            due_time=due_time,
            priority=parsed["priority"],
            remind_offset=remind_offset,
        )
        self.add_entry.delete(0, "end")
        self.refresh_nav()
        self.refresh_tasks()
        self.add_entry.focus_set()

    def toggle_task(self, task_id: int) -> None:
        self.db.toggle_complete(task_id)
        self.refresh_nav()
        self.refresh_tasks(keep_scroll=True)
        if self._current_task_id == task_id:
            self._load_detail(task_id)

    def open_task(self, task_id: int) -> None:
        self._flush_save()
        self._current_task_id = task_id
        self._load_detail(task_id)
        if not self.detail.winfo_ismapped():
            self.detail.grid()
        for widget in self._list_widgets:
            if isinstance(widget, TaskRow):
                widget.set_selected(widget.task_id == task_id)

    def close_detail(self, save: bool = True) -> None:
        if save:
            self._flush_save()
        self._current_task_id = None
        self._loading_detail = True
        try:
            self.detail.grid_remove()
        except Exception:
            pass
        self._loading_detail = False
        for widget in self._list_widgets:
            if isinstance(widget, TaskRow):
                widget.set_selected(False)

    def _delete_current(self) -> None:
        if self._current_task_id is None:
            return
        self._delete_task(self._current_task_id)

    def _complete_current(self) -> None:
        if self._current_task_id is None:
            return
        self.toggle_task(self._current_task_id)

    def _delete_task(self, task_id: int) -> None:
        row = self.db.get_task(task_id)
        if row is None:
            return
        if not dialogs.ask_confirm(
            self, "删除任务", f"确定要删除「{utils.truncate(row['title'], 24)}」吗？此操作不可撤销。"
        ):
            return
        self.db.delete_task(task_id)
        if self._current_task_id == task_id:
            self._current_task_id = None
            self.detail.grid_remove()
        self.refresh_nav()
        self.refresh_tasks()

    # ================================================== 右键菜单

    def task_menu(self, task_id: int, event) -> None:
        row = self.db.get_task(task_id)
        if row is None:
            return
        menu = tk.Menu(self, tearoff=0, font=(config.FONT_FAMILY, 9))
        completed = bool(row["completed"])
        menu.add_command(
            label="标记为未完成" if completed else "标记完成",
            command=lambda: self.toggle_task(task_id),
        )
        menu.add_separator()

        due_menu = tk.Menu(menu, tearoff=0, font=(config.FONT_FAMILY, 9))
        for label, delta in (("今天", 0), ("明天", 1), ("后天", 2)):
            due_menu.add_command(
                label=label,
                command=lambda d=delta: self._set_due(task_id, (date.today() + timedelta(days=d)).isoformat()),
            )
        due_menu.add_command(label="清除日期", command=lambda: self._set_due(task_id, None))
        menu.add_cascade(label="截止日期", menu=due_menu)

        prio_menu = tk.Menu(menu, tearoff=0, font=(config.FONT_FAMILY, 9))
        for level, name in ((3, "高"), (2, "中"), (1, "低"), (0, "无")):
            prio_menu.add_command(
                label=name, command=lambda p=level: self._set_priority(task_id, p)
            )
        menu.add_cascade(label="优先级", menu=prio_menu)

        move_menu = tk.Menu(menu, tearoff=0, font=(config.FONT_FAMILY, 9))
        for item in self.db.lists():
            move_menu.add_command(
                label=item["name"],
                command=lambda lid=int(item["id"]): self._move_task(task_id, lid),
            )
        menu.add_cascade(label="移动到清单", menu=move_menu)

        menu.add_separator()
        menu.add_command(label="删除任务", command=lambda: self._delete_task(task_id))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            menu.destroy()

    def _list_menu(self, event, list_id: int) -> None:
        row = next((r for r in self.db.lists() if int(r["id"]) == list_id), None)
        if row is None:
            return
        menu = tk.Menu(self, tearoff=0, font=(config.FONT_FAMILY, 9))
        menu.add_command(
            label="重命名 / 改颜色", command=lambda: self._edit_list(list_id, row["name"], row["color"])
        )
        menu.add_command(label="删除清单", command=lambda: self._delete_list(list_id, row["name"]))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            menu.destroy()

    # ================================================== 任务字段修改

    def _set_due(self, task_id: int, due_date: str | None) -> None:
        row = self.db.get_task(task_id)
        if row is None:
            return
        self.db.update_task(
            task_id,
            due_date=due_date,
            due_time=row["due_time"] if due_date else None,
            remind_offset=row["remind_offset"] if due_date else None,
        )
        self.refresh_nav()
        self.refresh_tasks(keep_scroll=True)
        if self._current_task_id == task_id:
            self._load_detail(task_id)

    def _set_priority(self, task_id: int, priority: int) -> None:
        self.db.update_task(task_id, priority=priority)
        self.refresh_tasks(keep_scroll=True)
        if self._current_task_id == task_id:
            self._load_detail(task_id)

    def _move_task(self, task_id: int, list_id: int) -> None:
        self.db.update_task(task_id, list_id=list_id)
        self.refresh_nav()
        self.refresh_tasks(keep_scroll=True)
        if self._current_task_id == task_id:
            self._load_detail(task_id)

    # ================================================== 清单操作

    def new_list(self) -> None:
        result = dialogs.ask_list(self, "新建清单")
        if not result:
            return
        name, color = result
        self.db.add_list(name, color)
        self.refresh_nav()

    def _edit_list(self, list_id: int, name: str, color: str) -> None:
        result = dialogs.ask_list(self, "编辑清单", name=name, color=color)
        if not result:
            return
        new_name, new_color = result
        self.db.rename_list(list_id, new_name, new_color)
        self.refresh_nav()
        self.refresh_tasks(keep_scroll=True)

    def _delete_list(self, list_id: int, name: str) -> None:
        if len(self.db.lists()) <= 1:
            dialogs.ask_confirm(
                self, "无法删除", "至少需要保留一个清单。", ok_text="知道了", danger=False
            )
            return
        if not dialogs.ask_confirm(
            self, "删除清单", f"删除「{name}」后，里面的任务会移动到默认清单。"
        ):
            return
        self.db.delete_list(list_id)
        self._list_items.pop(list_id, None)
        if self._view.get("id") == list_id:
            self.select_view("all")
        self.refresh_nav()
        self.refresh_tasks()

    # ================================================== 详情读写

    def _load_detail(self, task_id: int) -> None:
        row = self.db.get_task(task_id)
        if row is None:
            self.close_detail(save=False)
            return
        self._loading_detail = True
        try:
            self.d_title.delete("1.0", "end")
            self.d_title.insert("1.0", row["title"])

            self._refresh_list_menu()
            self.d_list.set(row["list_name"] or "")

            self.d_date.delete(0, "end")
            if row["due_date"]:
                self.d_date.insert(0, row["due_date"])
            self.d_time.delete(0, "end")
            if row["due_time"]:
                self.d_time.insert(0, row["due_time"])

            offset = row["remind_offset"]
            label = next(
                (name for name, value in config.REMIND_OPTIONS if value == offset), "不提醒"
            )
            self.d_remind.set(label)
            self.d_priority.set(config.PRIORITY_NAMES.get(int(row["priority"] or 0), "无"))

            self.d_notes.delete("1.0", "end")
            if row["notes"]:
                self.d_notes.insert("1.0", row["notes"])

            info = f"创建于 {utils.fmt_created(row['created_at'])}"
            if int(row["defer_count"] or 0):
                info += f" · 已自动延期 {int(row['defer_count'])} 次"
            if row["orig_due_date"]:
                info += f"（原定 {row['orig_due_date']}）"
            self.d_info.configure(text=info)
        finally:
            self._loading_detail = False

    def _refresh_list_menu(self) -> None:
        names = [row["name"] for row in self.db.lists()]
        self._list_map = {row["name"]: int(row["id"]) for row in self.db.lists()}
        try:
            self.d_list.configure(values=names)
        except Exception:
            pass

    def _on_detail_list(self, name: str) -> None:
        if self._loading_detail or self._current_task_id is None:
            return
        list_id = self._list_map.get(name)
        if list_id:
            self.db.update_task(self._current_task_id, list_id=list_id)
            self.refresh_nav()
            self.refresh_tasks(keep_scroll=True)

    def _schedule_save(self, immediate: bool = False) -> None:
        if self._loading_detail or self._current_task_id is None:
            return
        if self._save_job:
            try:
                self.after_cancel(self._save_job)
            except Exception:
                pass
            self._save_job = None
        if immediate:
            self._save_detail()
        else:
            self._save_job = self.after(600, self._save_detail)

    def _flush_save(self) -> None:
        if self._save_job:
            try:
                self.after_cancel(self._save_job)
            except Exception:
                pass
            self._save_job = None
            self._save_detail()

    def _save_detail(self) -> None:
        self._save_job = None
        if self._loading_detail or self._current_task_id is None:
            return
        row = self.db.get_task(self._current_task_id)
        if row is None:
            return

        title = self.d_title.get("1.0", "end").strip()
        if not title:
            title = row["title"]
            self.d_title.delete("1.0", "end")
            self.d_title.insert("1.0", title)

        raw_date = self.d_date.get().strip()
        due_date = parse_due_date(raw_date) if raw_date else None
        if raw_date and due_date is None:
            self.d_date.configure(border_color=config.DANGER)
            return
        self.d_date.configure(border_color=config.BORDER)

        raw_time = self.d_time.get().strip()
        due_time = parse_due_time(raw_time) if raw_time else None
        if raw_time and due_time is None:
            self.d_time.configure(border_color=config.DANGER)
            return
        self.d_time.configure(border_color=config.BORDER)

        if due_date is None:
            due_time = None

        offset = config.REMIND_VALUES.get(self.d_remind.get(), None)
        priority = {name: level for level, name in config.PRIORITY_NAMES.items()}.get(
            self.d_priority.get(), 0
        )
        notes = self.d_notes.get("1.0", "end").strip()

        changed = (
            title != row["title"]
            or due_date != row["due_date"]
            or due_time != row["due_time"]
            or offset != row["remind_offset"]
            or priority != int(row["priority"] or 0)
            or notes != (row["notes"] or "")
        )
        if not changed:
            return

        self.db.update_task(
            self._current_task_id,
            title=title,
            due_date=due_date,
            due_time=due_time,
            remind_offset=offset,
            priority=priority,
            notes=notes,
        )
        self.refresh_tasks(keep_scroll=True)
        self.refresh_nav()

    def _quick_date(self, delta: int) -> None:
        if self._current_task_id is None:
            return
        target = (date.today() + timedelta(days=delta)).isoformat()
        self.d_date.delete(0, "end")
        self.d_date.insert(0, target)
        self._save_detail()

    def _clear_date(self) -> None:
        if self._current_task_id is None:
            return
        self.d_date.delete(0, "end")
        self.d_time.delete(0, "end")
        self.d_remind.set("不提醒")
        self._save_detail()
        self._load_detail(self._current_task_id)

    # ================================================== 设置

    def open_settings(self) -> None:
        dialogs.SettingsDialog(self, self)

    def _apply_initial_settings(self) -> None:
        autostart_enabled = self.db.get_setting("autostart", "0") == "1"
        if autostart_enabled:
            autostart.sync(True)
        self.tray.set_autostart(autostart.is_enabled())
        if self.db.get_setting("always_on_top", "0") == "1":
            try:
                self.attributes("-topmost", True)
            except Exception:
                pass

    def sync_autostart_state(self) -> None:
        self.tray.set_autostart(autostart.is_enabled())
        self.db.set_setting("autostart", "1" if autostart.is_enabled() else "0")

    def toggle_autostart(self) -> None:
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()
        self.sync_autostart_state()

    def test_notification(self) -> None:
        mode = self.db.get_setting("notify_mode", config.DEFAULTS["notify_mode"])
        sound = self.db.get_setting("notify_sound", "1") == "1"

        if mode in ("toast", "both"):

            def worker() -> None:
                ok = self.notifier.show(
                    "轻待办 · 测试通知", "如果你看到这条消息，说明系统通知一切正常。"
                )
                if not ok:
                    self.post(
                        lambda: dialogs.ask_confirm(
                            self,
                            "系统通知发送失败",
                            f"通知没有发送成功：\n{self.notifier.last_error or '未知原因'}\n"
                            "可以把提醒方式改成「应用内弹窗」，它不受免打扰影响。",
                            ok_text="知道了",
                            danger=False,
                        )
                    )

            threading.Thread(target=worker, name="notify-test", daemon=True).start()

        if mode in ("popup", "both"):
            if sound and mode == "popup":
                sound_alert()
            self.show_test_popup()

    def clear_completed(self) -> None:
        if not dialogs.ask_confirm(self, "清空已完成", "将永久删除所有已完成的任务，确定继续吗？"):
            return
        removed = self.db.clear_completed()
        self.refresh_nav()
        self.refresh_tasks()
        self.post(lambda: self.tray.notify("已清理", f"删除了 {removed} 条已完成任务"))

    # ================================================== 提醒

    def show_reminder_popup(self, task_id: int) -> None:
        if any(popup.task_id == task_id for popup in self._popups):
            return
        row = self.db.get_task(task_id)
        if row is None or row["completed"]:
            return
        popup = ReminderPopup(
            self,
            row,
            index=len(self._popups),
            on_complete=self._popup_complete,
            on_snooze=self._popup_snooze,
            on_closed=self._popup_closed,
        )
        self._popups.append(popup)

    def _popup_closed(self, popup: ReminderPopup) -> None:
        if popup in self._popups:
            self._popups.remove(popup)
        for index, item in enumerate(self._popups):
            try:
                item._place(index)
            except Exception:
                pass

    def show_test_popup(self) -> None:
        task = {
            "id": 0,
            "title": "测试提醒：19:00 和产品过一下需求",
            "due_date": date.today().isoformat(),
            "due_time": datetime.now().strftime("%H:%M"),
            "list_name": "轻待办",
            "list_color": config.ACCENT,
            "notes": "",
        }
        popup = ReminderPopup(
            self,
            task,
            index=len(self._popups),
            on_complete=lambda tid: None,
            on_snooze=lambda tid: None,
            on_closed=self._popup_closed,
        )
        self._popups.append(popup)

    def _popup_complete(self, task_id: int) -> None:
        self.db.set_completed(task_id, True)
        self.refresh_nav()
        self.refresh_tasks(keep_scroll=True)
        if self._current_task_id == task_id:
            self._load_detail(task_id)

    def _popup_snooze(self, task_id: int) -> None:
        self.db.snooze(task_id, 10)
        self.refresh_tasks(keep_scroll=True)

    def _on_day_change(self, moved: int) -> None:
        self.refresh_nav()
        self.refresh_tasks()
        if moved:
            self.tray.notify(
                "新的一天", f"{moved} 项未完成的任务已自动延续到今天。"
            )

    # ================================================== 托盘 / 生命周期

    def _wire_tray(self) -> None:
        self.tray.on_open = self.show_window
        self.tray.on_new_task = self._tray_new_task
        self.tray.on_toggle_autostart = self.toggle_autostart
        self.tray.on_quit = self.quit_app

    def _tray_new_task(self) -> None:
        self.show_window()
        self.focus_add_entry()

    def focus_add_entry(self) -> None:
        try:
            self.add_entry.focus_set()
        except Exception:
            pass

    def focus_search(self) -> None:
        try:
            self.search_entry.focus_set()
        except Exception:
            pass

    def show_window(self) -> None:
        try:
            self.deiconify()
            self.state("normal")
            self.lift()
            topmost = self.db.get_setting("always_on_top", "0") == "1"
            self.attributes("-topmost", True)
            self.after(250, lambda: self.attributes("-topmost", topmost))
            self.focus_force()
        except Exception:
            pass

    def hide_to_tray(self) -> None:
        self._save_geometry()
        self.withdraw()
        if self.db.get_setting("tray_hint_shown", "0") != "1":
            self.db.set_setting("tray_hint_shown", "1")
            self.tray.notify("轻待办仍在后台运行", "提醒照常，双击托盘图标可以重新打开。")

    def _on_close(self) -> None:
        self._flush_save()
        if self.db.get_setting("close_to_tray", "1") == "1":
            self.hide_to_tray()
        else:
            self.quit_app()

    def quit_app(self) -> None:
        if not self._running:
            return
        self._running = False
        self._flush_save()
        self._save_geometry()
        for popup in list(self._popups):
            try:
                popup.close()
            except Exception:
                pass
        try:
            self.reminder.stop()
        except Exception:
            pass
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    # ================================================== 跨线程调度

    def post(self, func: Callable[[], None]) -> None:
        self._queue.put(func)

    def _pump(self) -> None:
        while True:
            try:
                func = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                func()
            except Exception:
                log.exception("queue task failed")
        if self._running:
            self.after(120, self._pump)

    def _toggle_show_completed(self) -> None:
        self._show_completed = bool(self.completed_check.get())
        self.refresh_tasks()
