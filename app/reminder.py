"""提醒调度：后台线程定时检查到期提醒，并在跨天时把未完成任务顺延。"""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Callable

from . import config, utils
from .db import Database
from .notifier import Notifier
from .sound import play_alert as sound_alert

log = logging.getLogger("lighttodo")


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
        log.info("提醒服务启动，检查间隔 %.0f 秒", self._interval)
        while not self._stop_event.wait(self._interval):
            try:
                self.tick()
            except Exception:
                # 后台线程不允许崩掉整个应用，但异常要留痕
                log.exception("提醒检查失败")
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

        # 1）正常到点提醒
        for task in self._db.due_reminders():
            self._db.mark_reminded(int(task["id"]))
            self._notify(task, use_toast, use_popup, sound)

        # 2）过期后未处理：每隔一段时间再提醒一次
        repeat_on, minutes = self._repeat_settings()
        if repeat_on and (use_toast or use_popup):
            self._db.arm_repeat_reminders(minutes)
            for task in self._db.due_repeat_reminders():
                self._db.mark_nagged(int(task["id"]), minutes)
                self._notify(task, use_toast, use_popup, sound, repeat=True)

    def _repeat_settings(self) -> tuple[bool, int]:
        """读「过期重复提醒」开关与间隔（分钟）。"""
        on = self._db.get_setting("repeat_remind", config.DEFAULTS["repeat_remind"]) == "1"
        try:
            minutes = int(self._db.get_setting(
                "repeat_remind_minutes", str(config.REPEAT_REMIND_DEFAULT)
            ))
        except (TypeError, ValueError):
            minutes = config.REPEAT_REMIND_DEFAULT
        if minutes <= 0:
            minutes = config.REPEAT_REMIND_DEFAULT
        return on, minutes

    def _notify(self, task, use_toast: bool, use_popup: bool, sound: bool, repeat: bool = False) -> None:
        task_id = int(task["id"])
        body = utils.describe_due(task["due_date"], task["due_time"])
        if repeat:
            body = f"已过期 · {body}"
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
