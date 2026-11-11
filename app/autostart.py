"""开机自启：写入 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run。"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

from . import config

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "LightTodo"


def _entry_script() -> Path:
    return config.app_dir() / "轻待办.pyw"


def command_line() -> str:
    """便携版用 exe 本身；源码运行用 pythonw 启动脚本。"""
    if config.is_frozen():
        return f'"{Path(sys.executable)}" --minimized'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    return f'"{pythonw}" "{_entry_script()}" --minimized'


def _open(access: int = winreg.KEY_READ):
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access)


def current_value() -> str | None:
    try:
        with _open() as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def is_enabled() -> bool:
    return bool(current_value())


def enable() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command_line())
        return True
    except OSError:
        return False


def disable() -> bool:
    try:
        with _open(winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
        return True
    except OSError:
        return False


def sync(enabled: bool) -> None:
    """如果已开启但路径变了（比如移动了文件夹），自动修正。"""
    value = current_value()
    if not value:
        if enabled:
            enable()
        return
    if value.strip() != command_line():
        enable()
