"""提醒调度：后台线程定时检查到期提醒，并在跨天时把未完成任务顺延。"""

from __future__ import annotations

import threading
from datetime import date
from typing import Callable

from . import config, utils
from .db import Database
from .notifier import Notifier
from .sound import play_alert as sound_alert


class ReminderService(threading.Thread):
    def __init__(
        self,
        db: Database,
        notifier: Notifier,
        post: Callable[[Callable], None],
        interval: float = 15.0,
    ):
        super().__init__(name="reminder", daemon=True)
        self._db = db
        self._notifier = notifier
        self._post = post
        self._interval = interval
        self._stop_event = threading.Event()
        self._day = date.today()
        self.on_reminder: Callable[[int], None] | None = None
        self.on_day_change: Callable[[int], None] | None = None

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self.tick()
            except Exception:
                # 后台线程不允许崩掉整个应用
                continue

    # -------------------------------------------------- 单次检查

    def tick(self) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            moved = self._db.rollover()
            if moved and self.on_day_change:
                self._post(lambda n=moved: self.on_day_change(n))

        mode = self._db.get_setting("notify_mode", config.DEFAULTS["notify_mode"])
        sound = self._db.get_setting("notify_sound", "1") == "1"
        use_toast = mode in ("toast", "both")
        use_popup = mode in ("popup", "both") and self.on_reminder is not None

        for task in self._db.due_reminders():
            task_id = int(task["id"])
            self._db.mark_reminded(task_id)
            body = f"{utils.describe_due(task['due_date'], task['due_time'])}"
            if task["list_name"]:
                body = f"{body} · {task['list_name']}"
            if use_toast:
                # 系统通知自带声音；只在纯弹窗模式下自己补一声
                self._notifier.show(task["title"], body, sound=sound)
            elif use_popup and sound:
                sound_alert()
            if use_popup:
                self._post(lambda tid=task_id: self.on_reminder(tid))

    def check_now(self) -> None:
        """让 UI 手动触发一次检查（如设置里点"测试提醒"）。"""
        try:
            self.tick()
        except Exception:
            pass
