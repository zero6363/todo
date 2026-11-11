"""提醒提示音：走系统事件音，Windows 免打扰不会拦截。"""

from __future__ import annotations

import threading


def _play_once() -> None:
    try:
        import winsound

        for alias in ("SystemNotification", "Notification.Reminder", "SystemAsterisk"):
            try:
                winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
                return
            except Exception:
                continue
        winsound.MessageBeep()
    except Exception:
        pass


def play_alert() -> None:
    """异步播放一声提示，不阻塞界面。"""
    threading.Thread(target=_play_once, name="alert-sound", daemon=True).start()
