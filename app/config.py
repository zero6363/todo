"""全局配置：路径、颜色、常量。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "轻待办"
APP_ID = "LightTodo.App"
APP_VERSION = "1.4.5"

# 只给日期、没给具体时间时的默认时刻（同时作为提醒时刻）
DEFAULT_DUE_CLOCK = "14:00"
DEFAULT_DUE_HOUR = 14

# ---------------------------------------------------------------- 路径


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """程序目录。便携版即 exe 所在目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """只读资源目录（onefile 打包后位于临时解包目录）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return app_dir()


def asset_path(name: str) -> Path:
    return resource_dir() / "assets" / name


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("1", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


_data_dir_cache: Path | None = None


def data_dir() -> Path:
    """数据目录：优先程序同级的 data（真正的便携），不可写时退回 AppData。"""
    global _data_dir_cache
    if _data_dir_cache is not None:
        return _data_dir_cache

    candidate = app_dir() / "data"
    if _writable(candidate):
        _data_dir_cache = candidate
        return candidate

    fallback = Path(os.environ.get("APPDATA", str(Path.home()))) / "LightTodo"
    fallback.mkdir(parents=True, exist_ok=True)
    _data_dir_cache = fallback
    return fallback


def db_path() -> Path:
    return data_dir() / "todo.db"


# ---------------------------------------------------------------- 主题

BG = "#FFFFFF"
SIDEBAR_BG = "#F4F5F7"
PANEL_BG = "#FBFBFC"
BORDER = "#E8EAEE"
HOVER = "#F1F3F6"
SELECTED = "#E9F0FF"
ACCENT = "#3A6FF7"
ACCENT_HOVER = "#2B5EE2"
ACCENT_SOFT = "#E9F0FF"
TEXT = "#1D2129"
TEXT_SUB = "#5C6470"
TEXT_MUTED = "#99A1AC"
DANGER = "#E5484D"
DANGER_SOFT = "#FDECEC"
WARN = "#E8833A"
SUCCESS = "#13935A"

PRIORITY_COLORS = {0: "", 1: "#4C9AFF", 2: "#F5A524", 3: "#E5484D"}
PRIORITY_NAMES = {0: "无", 1: "低", 2: "中", 3: "高"}

FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Consolas"

# 清单可选颜色
LIST_COLORS = ["#3A6FF7", "#E5484D", "#F5A524", "#13935A", "#8B5CF6", "#EC4899", "#0EA5E9", "#64748B"]

# 提醒偏移（分钟）：标签 -> 值
REMIND_OPTIONS: list[tuple[str, int | None]] = [
    ("不提醒", None),
    ("准时", 0),
    ("提前 5 分钟", 5),
    ("提前 15 分钟", 15),
    ("提前 30 分钟", 30),
    ("提前 1 小时", 60),
    ("提前 1 天", 1440),
]
REMIND_LABELS = [label for label, _ in REMIND_OPTIONS]
REMIND_VALUES = {label: value for label, value in REMIND_OPTIONS}

# 提醒卡片上的「稍后」快捷选项
SNOOZE_OPTIONS: list[tuple[str, int]] = [
    ("10 分钟", 10),
    ("30 分钟", 30),
    ("1 小时", 60),
]
SNOOZE_DEFAULT = 10
SNOOZE_MAX = 10080  # 7 天

# 循环任务：(标签, 规则)。规则约定见 utils.next_repeat_date
REPEAT_OPTIONS: list[tuple[str, str | None]] = [
    ("不重复", None),
    ("每天", "daily"),
    ("工作日", "weekdays"),
    ("每周", "weekly"),
    ("每月", "monthly"),
    ("每 2 天", "interval:2:day"),
    ("每 3 天", "interval:3:day"),
    ("每 7 天", "interval:7:day"),
    ("每 2 周", "interval:2:week"),
]
REPEAT_LABELS = [label for label, _ in REPEAT_OPTIONS]
REPEAT_VALUES = {label: rule for label, rule in REPEAT_OPTIONS}
REPEAT_TITLES = {rule: label for label, rule in REPEAT_OPTIONS if rule}

# 屏幕右下角同时最多显示几张提醒卡片，多的排队
POPUP_MAX_VISIBLE = 3

# 提醒方式：应用内弹窗 / 系统通知 / 两者
NOTIFY_MODES: list[tuple[str, str]] = [
    ("应用内弹窗", "popup"),
    ("系统通知", "toast"),
    ("两者都要", "both"),
]
NOTIFY_MODE_LABELS = [label for label, _ in NOTIFY_MODES]
NOTIFY_MODE_VALUES = {label: value for label, value in NOTIFY_MODES}
NOTIFY_MODE_TITLES = {value: label for label, value in NOTIFY_MODES}

# 默认设置
DEFAULTS = {
    "autostart": "0",
    "close_to_tray": "1",
    "notify_mode": "popup",
    "notify_sound": "1",
    "always_on_top": "0",
}
