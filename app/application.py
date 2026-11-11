"""应用入口：单实例、日志、装配 Fluent UI。"""

from __future__ import annotations

import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import config
from .db import Database
from .icon import runtime_icon
from .notifier import Notifier
from .qt import theme
from .qt.main_window import MainWindow

log = logging.getLogger("lighttodo")

ERROR_ALREADY_EXISTS = 183


def setup_logging() -> None:
    try:
        handler = RotatingFileHandler(
            config.data_dir() / "app.log", maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
    except Exception:
        pass


def _single_instance_mutex():
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, "Local\\LightTodo_SingleInstance")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            ctypes.windll.user32.MessageBoxW(
                None,
                "轻待办已经在运行啦，请查看任务栏右下角的托盘图标。",
                config.APP_NAME,
                0x40,
            )
            return None
        return handle
    except Exception:
        return True


def run() -> None:
    setup_logging()
    mutex = _single_instance_mutex()
    if mutex is None:
        return

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    theme.apply_theme()

    start_minimized = "--minimized" in sys.argv[1:]
    try:
        icon_path = runtime_icon(config.data_dir() / "icon.ico")
        app.setWindowIcon(QIcon(str(icon_path)))

        db = Database(config.db_path())
        notifier = Notifier(icon_path)
        moved = db.rollover()

        window = MainWindow(db, notifier, start_minimized=start_minimized)
        if not start_minimized:
            window.show()

        if moved:
            QTimer.singleShot(
                2000,
                lambda: window.tray.notify(
                    "任务已延续", f"{moved} 项未完成的任务已自动延续到今天。"
                ),
            )

        def excepthook(exc_type, exc_value, exc_tb):
            log.error("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))

        sys.excepthook = excepthook
        log.info(
            "启动完成：frozen=%s data=%s 延续=%s",
            config.is_frozen(),
            config.data_dir(),
            moved,
        )
        sys.exit(app.exec())
    except Exception:
        log.exception("应用启动失败")
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"轻待办启动失败，详情见日志：\n{config.data_dir() / 'app.log'}",
                config.APP_NAME,
                0x10,
            )
        except Exception:
            pass
        raise
