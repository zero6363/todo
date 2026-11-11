"""对话框：确认、清单编辑、设置。"""

from __future__ import annotations

import os
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from .. import autostart, config
from . import theme
from .components import SegmentedControl


class BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, width: int = 460):
        super().__init__(parent)
        self.parent_window = parent
        self.result = None
        self.title(title)
        self.configure(fg_color=config.BG)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._target_width = width
        self.withdraw()
        try:
            icon = config.data_dir() / "icon.ico"
            if icon.exists():
                self.iconbitmap(str(icon))
        except Exception:
            pass

    # -------------------------------------------------- 展示

    def _finalize(self) -> None:
        self.update_idletasks()
        width = max(self._target_width, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        self.update_idletasks()
        parent = self.parent_window
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px, py, pw, ph = 200, 200, 1000, 700
        x = px + max((pw - width) // 2, 0)
        y = py + max((ph - height) // 2, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.lift()
        try:
            self.grab_set()
        except Exception:
            pass
        self.focus_force()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    # -------------------------------------------------- 通用部件

    def header(self, title: str, subtitle: str = "") -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=24, pady=(20, 8))
        ctk.CTkLabel(
            frame, text=title, anchor="w", font=theme.font(17, "bold"), text_color=config.TEXT
        ).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(
                frame,
                text=subtitle,
                anchor="w",
                justify="left",
                font=theme.font(11),
                text_color=config.TEXT_MUTED,
                wraplength=380,
            ).pack(anchor="w", pady=(4, 0))
        return frame

    def footer(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=24, pady=(8, 20), side="bottom")
        return frame


class ConfirmDialog(BaseDialog):
    def __init__(self, parent, title: str, message: str, ok_text: str = "确定", danger: bool = True):
        super().__init__(parent, title, width=420)
        self.header(title, message)
        bar = self.footer()

        ctk.CTkButton(
            bar,
            text="取消",
            width=88,
            height=34,
            corner_radius=8,
            fg_color="transparent",
            hover_color=config.HOVER,
            text_color=config.TEXT_SUB,
            border_width=1,
            border_color=config.BORDER,
            command=self._cancel,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            bar,
            text=ok_text,
            width=88,
            height=34,
            corner_radius=8,
            fg_color=config.DANGER if danger else config.ACCENT,
            hover_color="#C93B40" if danger else config.ACCENT_HOVER,
            command=self._ok,
        ).pack(side="right")

        self._finalize()
        self.wait_window(self)

    def _ok(self) -> None:
        self.result = True
        self.destroy()


class ListDialog(BaseDialog):
    """新建 / 重命名清单，可挑颜色。"""

    def __init__(self, parent, title: str = "新建清单", name: str = "", color: str = config.ACCENT):
        super().__init__(parent, title, width=420)
        self.header(title, "起个名字，并选一个颜色便于区分。")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=24, pady=(4, 0))

        self.entry = ctk.CTkEntry(
            body,
            height=38,
            corner_radius=8,
            font=theme.font(13),
            fg_color=config.BG,
            border_color=config.BORDER,
            placeholder_text="清单名称",
        )
        self.entry.pack(fill="x")
        if name:
            self.entry.insert(0, name)

        swatches = ctk.CTkFrame(self, fg_color="transparent")
        swatches.pack(fill="x", padx=24, pady=(14, 0))
        ctk.CTkLabel(
            swatches, text="颜色", font=theme.font(12), text_color=config.TEXT_SUB, width=40
        ).pack(side="left")

        self._color = color
        self._swatch_buttons: dict[str, ctk.CTkButton] = {}
        for item in config.LIST_COLORS:
            btn = ctk.CTkButton(
                swatches,
                text="",
                width=22,
                height=22,
                corner_radius=11,
                fg_color=item,
                hover_color=item,
                border_width=2,
                border_color=config.BG if item != color else config.TEXT,
                command=lambda c=item: self._pick(c),
            )
            btn.pack(side="left", padx=4)
            self._swatch_buttons[item] = btn

        bar = self.footer()
        ctk.CTkButton(
            bar,
            text="取消",
            width=88,
            height=34,
            corner_radius=8,
            fg_color="transparent",
            hover_color=config.HOVER,
            text_color=config.TEXT_SUB,
            border_width=1,
            border_color=config.BORDER,
            command=self._cancel,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            bar,
            text="保存",
            width=88,
            height=34,
            corner_radius=8,
            fg_color=config.ACCENT,
            hover_color=config.ACCENT_HOVER,
            command=self._ok,
        ).pack(side="right")

        self.entry.bind("<Return>", lambda e: self._ok())
        self.entry.focus_set()

        self._finalize()
        self.wait_window(self)

    def _pick(self, color: str) -> None:
        self._color = color
        for item, btn in self._swatch_buttons.items():
            btn.configure(border_color=config.TEXT if item == color else config.BG)

    def _ok(self) -> None:
        name = self.entry.get().strip()
        if not name:
            self.entry.configure(border_color=config.DANGER)
            return
        self.result = (name, self._color)
        self.destroy()


def ask_confirm(parent, title: str, message: str, ok_text: str = "删除", danger: bool = True) -> bool:
    dialog = ConfirmDialog(parent, title, message, ok_text=ok_text, danger=danger)
    return bool(dialog.result)


def ask_list(parent, title: str = "新建清单", name: str = "", color: str = config.ACCENT):
    dialog = ListDialog(parent, title=title, name=name, color=color)
    return dialog.result


class SettingsDialog(BaseDialog):
    def __init__(self, parent, app):
        super().__init__(parent, "设置", width=520)
        self.app = app
        self.db = app.db

        self.header("设置", f"{config.APP_NAME} v{config.APP_VERSION} · 便携版 · 数据保存在程序目录 data 文件夹")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(4, 0))

        self._switch(
            body,
            "开机自动启动",
            "登录 Windows 后自动在托盘运行（写入当前用户启动项）。",
            "autostart",
            self._toggle_autostart,
        )
        self._switch(
            body,
            "关闭窗口时最小化到托盘",
            "点右上角 × 不退出程序，继续在后台提醒。",
            "close_to_tray",
        )
        self._switch(body, "窗口置顶", "让主窗口保持在其他窗口上方。", "always_on_top", self._toggle_topmost)
        self._notify_mode_row(body)
        self._switch(
            body,
            "提醒声音",
            "应用内弹窗时播放一声系统提示音（免打扰不会拦截）。",
            "notify_sound",
        )

        test_row = ctk.CTkFrame(body, fg_color="transparent")
        test_row.pack(fill="x", pady=(6, 2))
        ctk.CTkButton(
            test_row,
            text="发送测试通知",
            width=120,
            height=32,
            corner_radius=8,
            fg_color=config.ACCENT_SOFT,
            hover_color="#DCE7FF",
            text_color=config.ACCENT,
            command=self.app.test_notification,
        ).pack(side="left")

        ctk.CTkLabel(
            body,
            text=f"数据文件：{config.db_path()}",
            anchor="w",
            justify="left",
            wraplength=440,
            font=theme.font(11),
            text_color=config.TEXT_MUTED,
        ).pack(fill="x", pady=(12, 4))

        data_row = ctk.CTkFrame(body, fg_color="transparent")
        data_row.pack(fill="x")
        ctk.CTkButton(
            data_row,
            text="打开数据目录",
            width=110,
            height=32,
            corner_radius=8,
            fg_color="transparent",
            hover_color=config.HOVER,
            text_color=config.TEXT_SUB,
            border_width=1,
            border_color=config.BORDER,
            command=lambda: os.startfile(str(config.data_dir())),
        ).pack(side="left")
        ctk.CTkButton(
            data_row,
            text="清空已完成任务",
            width=120,
            height=32,
            corner_radius=8,
            fg_color="transparent",
            hover_color=config.DANGER_SOFT,
            text_color=config.DANGER,
            border_width=1,
            border_color=config.BORDER,
            command=self.app.clear_completed,
        ).pack(side="left", padx=(8, 0))

        bar = self.footer()
        ctk.CTkButton(
            bar,
            text="关闭",
            width=88,
            height=34,
            corner_radius=8,
            fg_color=config.ACCENT,
            hover_color=config.ACCENT_HOVER,
            command=self.destroy,
        ).pack(side="right")

        self._finalize()

    # -------------------------------------------------- 行

    def _switch(self, parent, title: str, desc: str, key: str, callback: Callable | None = None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        row.grid_columnconfigure(0, weight=1)

        texts = ctk.CTkFrame(row, fg_color="transparent")
        texts.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            texts, text=title, anchor="w", font=theme.font(13), text_color=config.TEXT
        ).pack(anchor="w")
        ctk.CTkLabel(
            texts,
            text=desc,
            anchor="w",
            justify="left",
            font=theme.font(11),
            text_color=config.TEXT_MUTED,
            wraplength=360,
        ).pack(anchor="w")

        value = self.db.get_setting(key, config.DEFAULTS.get(key, "0")) == "1"
        var = tk.BooleanVar(value=value)
        switch = ctk.CTkSwitch(
            row,
            text="",
            variable=var,
            width=46,
            progress_color=config.ACCENT,
            command=lambda: self._on_switch(key, var, callback),
        )
        switch.grid(row=0, column=1, padx=(12, 0))
        return switch

    def _on_switch(self, key: str, var: tk.BooleanVar, callback: Callable | None) -> None:
        value = bool(var.get())
        self.db.set_setting(key, "1" if value else "0")
        if callback:
            callback(value)

    def _notify_mode_row(self, parent) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(
            block, text="提醒方式", anchor="w", font=theme.font(13), text_color=config.TEXT
        ).pack(anchor="w")
        ctk.CTkLabel(
            block,
            text="应用内弹窗浮在屏幕右下角，开着 Windows 免打扰也能看到；"
            "系统通知会进右下角通知中心，勿扰时会被静音。",
            anchor="w",
            justify="left",
            wraplength=430,
            font=theme.font(11),
            text_color=config.TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 6))

        current = self.db.get_setting("notify_mode", config.DEFAULTS["notify_mode"])
        self.notify_mode = SegmentedControl(
            block,
            values=config.NOTIFY_MODE_LABELS,
            height=30,
            command=self._on_notify_mode,
        )
        self.notify_mode.pack(fill="x")
        self.notify_mode.set(config.NOTIFY_MODE_TITLES.get(current, "应用内弹窗"))

    def _on_notify_mode(self, label: str) -> None:
        mode = config.NOTIFY_MODE_VALUES.get(label, "popup")
        self.db.set_setting("notify_mode", mode)

    def _toggle_autostart(self, value: bool) -> None:
        ok = autostart.enable() if value else autostart.disable()
        if not ok:
            self.db.set_setting("autostart", "0")
        self.app.sync_autostart_state()

    def _toggle_topmost(self, value: bool) -> None:
        try:
            self.app.attributes("-topmost", value)
        except Exception:
            pass
