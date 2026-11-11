"""应用内提醒卡片：右下角浮现，勿扰模式下也能看到。"""

from __future__ import annotations

import ctypes
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from .. import config, utils
from . import theme

SPI_GETWORKAREA = 0x0030


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def work_area() -> tuple[int, int, int, int]:
    try:
        rect = _RECT()
        ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        if rect.right > rect.left and rect.bottom > rect.top:
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, 1280, 800


class ReminderPopup(ctk.CTkToplevel):
    WIDTH = 356
    HEIGHT = 136

    def __init__(
        self,
        master,
        task,
        index: int,
        on_complete: Callable[[int], None],
        on_snooze: Callable[[int], None],
        on_closed: Callable[["ReminderPopup"], None],
    ):
        super().__init__(master)
        self.task = task
        self.task_id = int(task["id"])
        self._on_complete = on_complete
        self._on_snooze = on_snooze
        self._on_closed = on_closed
        self._closed = False

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0)
        self.configure(fg_color=config.BG)

        wrapper = ctk.CTkFrame(self, fg_color=config.BG, corner_radius=10, border_width=1, border_color=config.BORDER)
        wrapper.pack(fill="both", expand=True)

        accent_color = config.ACCENT
        try:
            accent_color = task["list_color"] or config.ACCENT
        except (KeyError, IndexError):
            accent_color = config.ACCENT
        accent = ctk.CTkFrame(wrapper, width=4, corner_radius=2, fg_color=accent_color)
        accent.pack(side="left", fill="y", padx=(1, 0), pady=1)

        content = ctk.CTkFrame(wrapper, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=(12, 12), pady=(10, 10))

        top = ctk.CTkFrame(content, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top, text="任务提醒", font=theme.font(11, "bold"), text_color=config.ACCENT, anchor="w"
        ).pack(side="left")
        ctk.CTkButton(
            top,
            text="×",
            width=20,
            height=20,
            corner_radius=4,
            fg_color="transparent",
            hover_color=config.HOVER,
            text_color=config.TEXT_MUTED,
            font=theme.font(13),
            command=self.close,
        ).pack(side="right")

        ctk.CTkLabel(
            content,
            text=utils.truncate(task["title"], 42),
            font=theme.font(14, "bold"),
            text_color=config.TEXT,
            anchor="w",
            justify="left",
            wraplength=300,
        ).pack(fill="x", pady=(2, 0))

        meta = utils.describe_due(task["due_date"], task["due_time"])
        if task["list_name"]:
            meta = f"{meta} · {task['list_name']}"
        ctk.CTkLabel(
            content, text=meta, font=theme.font(11), text_color=config.TEXT_MUTED, anchor="w"
        ).pack(fill="x", pady=(2, 6))

        buttons = ctk.CTkFrame(content, fg_color="transparent")
        buttons.pack(fill="x", side="bottom")
        ctk.CTkButton(
            buttons,
            text="完成",
            width=64,
            height=26,
            corner_radius=6,
            font=theme.font(11),
            fg_color=config.ACCENT,
            hover_color=config.ACCENT_HOVER,
            command=self._complete,
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text="稍后 10 分钟",
            width=96,
            height=26,
            corner_radius=6,
            font=theme.font(11),
            fg_color="transparent",
            hover_color=config.HOVER,
            text_color=config.TEXT_SUB,
            border_width=1,
            border_color=config.BORDER,
            command=self._snooze,
        ).pack(side="left", padx=(8, 0))

        self._place(index)
        self._fade_in()
        # 作为主要提醒渠道，停留久一点，避免人不在屏幕前就错过
        self.after(120000, self.close)

    # -------------------------------------------------- 位置与动画

    def _place(self, index: int) -> None:
        left, _top, right, bottom = work_area()
        x = right - self.WIDTH - 18
        y = bottom - (index + 1) * (self.HEIGHT + 12) - 8
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _fade_in(self, step: int = 0) -> None:
        alpha = min(0.96, 0.24 * (step + 1))
        try:
            self.attributes("-alpha", alpha)
        except Exception:
            return
        if alpha < 0.96:
            self.after(24, lambda: self._fade_in(step + 1))

    # -------------------------------------------------- 动作

    def _complete(self) -> None:
        self._on_complete(self.task_id)
        self.close()

    def _snooze(self) -> None:
        self._on_snooze(self.task_id)
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._on_closed(self)
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _grab_focus(self) -> None:
        try:
            self.lift()
        except Exception:
            pass
