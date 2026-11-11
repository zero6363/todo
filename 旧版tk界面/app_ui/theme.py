"""字体与控件工厂（字体必须在 Tk 根窗口创建之后生成）。"""

from __future__ import annotations

import customtkinter as ctk

from .. import config


_font_cache: dict[tuple, "ctk.CTkFont"] = {}


def font(size: int = 13, weight: str = "normal", overstrike: bool = False) -> ctk.CTkFont:
    key = (size, weight, overstrike)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    instance = ctk.CTkFont(
        family=config.FONT_FAMILY, size=size, weight=weight, overstrike=overstrike
    )
    _font_cache[key] = instance
    return instance


def mono(size: int = 12) -> ctk.CTkFont:
    return ctk.CTkFont(family=config.MONO_FAMILY, size=size)


def apply_appearance() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")


def transparent_button(master, text: str, command, **kwargs) -> ctk.CTkButton:
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        fg_color="transparent",
        hover_color=config.HOVER,
        text_color=config.TEXT_SUB,
        font=font(12),
        height=30,
        corner_radius=6,
        **kwargs,
    )
