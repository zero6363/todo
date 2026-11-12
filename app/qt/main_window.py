"""主窗口：FluentWindow + 视图页 + 详情面板 + 托盘 + 提醒调度。"""

from __future__ import annotations

import logging
import queue
import threading
from datetime import date, datetime, timedelta

from PySide6.QtCore import QByteArray, QPoint, QTimer, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    Action,
    FluentIcon as FIF,
    FluentWindow,
    NavigationItemPosition,
    RoundMenu,
)

from .. import autostart, config, utils
from ..db import Database
from ..icon import runtime_icon
from ..notifier import Notifier
from ..reminder import ReminderService
from ..sound import play_alert as sound_alert
from . import dialogs, theme
from .detail_panel import DetailPanel
from .reminder_popup import ReminderPopup
from .settings_page import SettingsPage
from .task_page import TaskPage
from .tray import TrayIcon

log = logging.getLogger("lighttodo")

VIEWS = [
    ("today", "今天", FIF.HOME),
    ("next7", "最近 7 天", FIF.CALENDAR),
    ("all", "全部", FIF.MENU),
    ("inbox", "收集箱", FIF.MAIL),
    ("completed", "已完成", FIF.COMPLETED),
]


class MainWindow(FluentWindow):
    def __init__(self, db: Database, notifier: Notifier, start_minimized: bool = False):
        super().__init__()
        self.db = db
        self.notifier = notifier
        self.current_task_id: int | None = None
        self._queue: queue.Queue = queue.Queue()
        self._popups: list[ReminderPopup] = []
        self._popup_queue: list[int] = []
        self._quitting = False
        self._list_items: dict[int, object] = {}
        self._new_list_item = None
        self.list_pages: dict[int, TaskPage] = {}
        self._reverting_page = False
        self._last_page_index = 0

        self.setWindowTitle(config.APP_NAME)
        try:
            self._base_icon = QIcon(str(runtime_icon(config.data_dir() / "icon.ico")))
        except Exception:
            self._base_icon = QIcon()
        self.setWindowIcon(self._base_icon)
        self.resize(1240, 800)
        self.setMinimumSize(1040, 660)
        try:
            self.setMicaEffectEnabled(True)
        except Exception:
            pass

        self.navigationInterface.setExpandWidth(236)
        self.navigationInterface.setMinimumExpandWidth(980)
        try:
            self.navigationInterface.panel.setReturnButtonVisible(False)
        except Exception:
            pass

        self._build_pages()
        self._build_list_nav()
        self._build_detail()
        self._build_tray()
        # 默认显示「全部」视图
        self.select_view("all")
        self._last_page_index = self.stackedWidget.indexOf(self.pages["all"])
        self.navigationInterface.expand(useAni=False)
        self._start_services()
        self._restore_geometry()
        self.refresh_all()

        self._bind_shortcuts()
        self.stackedWidget.currentChanged.connect(self._on_page_changed)

        self._pump_timer = QTimer(self)
        self._pump_timer.timeout.connect(self._pump)
        self._pump_timer.start(250)

        if start_minimized:
            self.hide()

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_task)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self.switchTo(self.settings_page))
        QShortcut(QKeySequence("Escape"), self, activated=self.close_detail)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_detail)

    def save_detail(self) -> None:
        if self.detail.isVisible():
            self.detail.save()

    def _focus_search(self) -> None:
        page = self.current_page()
        if page:
            page.search.setFocus()

    # ================================================== 构建

    def _build_pages(self) -> None:
        self.pages: dict[str, TaskPage] = {}
        for key, text, icon in VIEWS:
            page = TaskPage(self, key)
            self.addSubInterface(page, icon, text)
            self.pages[key] = page

        self.settings_page = SettingsPage(self)
        self.addSubInterface(
            self.settings_page, FIF.SETTING, "设置", position=NavigationItemPosition.BOTTOM
        )

    def _build_list_nav(self) -> None:
        self.navigationInterface.addSeparator()
        self.navigationInterface.addItemHeader("我的清单")
        self._rebuild_list_items()

    def _rebuild_list_items(self) -> None:
        for list_id in list(self._list_items):
            try:
                self.navigationInterface.removeWidget(f"list_{list_id}")
            except Exception:
                pass
        self._list_items.clear()
        if self._new_list_item is not None:
            try:
                self.navigationInterface.removeWidget("new_list")
            except Exception:
                pass
            self._new_list_item = None

        for row in self.db.lists():
            list_id = int(row["id"])
            item = self.navigationInterface.addItem(
                f"list_{list_id}",
                theme.dot_icon(row["color"]),
                row["name"],
                onClick=lambda *_, i=list_id: self.show_list(i),
                selectable=True,
                tooltip=row["name"],
            )
            self._list_items[list_id] = item

        self._new_list_item = self.navigationInterface.addItem(
            "new_list",
            FIF.ADD,
            "新建清单",
            onClick=lambda *_: self.new_list(),
            selectable=False,
        )

    def _build_detail(self) -> None:
        self.detail = DetailPanel(self)
        self.widgetLayout.addWidget(self.detail)
        self.detail.hide()

    def _build_tray(self) -> None:
        icon = QIcon(str(config.data_dir() / "icon.ico"))
        self.tray = TrayIcon(icon, self)
        self.notifier.set_fallback(self.tray.notify)
        self.tray.set_autostart(autostart.is_enabled())

    def _start_services(self) -> None:
        self.reminder = ReminderService(self.db, self.notifier, self.post)
        self.reminder.on_reminder = self.show_reminder_popup
        self.reminder.on_day_change = self._on_day_change
        self.reminder.start()

    # ================================================== 数据

    def query_tasks(self, view_type: str, view_id, show_completed: bool, search: str = ""):
        return self.db.tasks_for_view(
            view_type, view_id=view_id, search=search, show_completed=show_completed
        )

    def view_title(self, view_type: str, view_id) -> str:
        if view_type == "list":
            row = next((r for r in self.db.lists() if int(r["id"]) == view_id), None)
            return row["name"] if row else "清单"
        return next((text for key, text, _ in VIEWS if key == view_type), "任务")

    def header_text(self, view_type: str, view_id, shown: int, searching: bool):
        title = self.view_title(view_type, view_id)
        if searching:
            return title, f"找到 {shown} 项"
        if view_type == "completed":
            return title, f"共 {shown} 项已完成"
        counts = self.db.counts()
        pending = counts.get(view_type, shown) if view_type != "list" else shown
        return title, f"{pending} 项待完成"

    def refresh_current(self) -> None:
        page = self.stackedWidget.currentWidget()
        if isinstance(page, TaskPage):
            page.refresh()
        self.refresh_counts()

    def refresh_all(self) -> None:
        for page in self.pages.values():
            page.refresh()
        for page in self.list_pages.values():
            page.refresh()
        self.refresh_counts()

    def refresh_counts(self) -> None:
        counts = self.db.counts()
        today = counts.get("today", 0)
        self.setWindowTitle(f"{config.APP_NAME} · 今天 {today} 项")
        if hasattr(self, "tray"):
            self.tray.set_today_count(today)

    def current_page(self) -> TaskPage | None:
        page = self.stackedWidget.currentWidget()
        return page if isinstance(page, TaskPage) else None

    # ================================================== 视图切换

    def show_list(self, list_id: int) -> None:
        page = self._ensure_list_page(list_id)
        self.stackedWidget.setCurrentWidget(page, popOut=False)
        try:
            self.navigationInterface.setCurrentItem(f"list_{list_id}")
        except Exception:
            pass

    def _ensure_list_page(self, list_id: int) -> TaskPage:
        page = self.list_pages.get(list_id)
        if page is not None:
            return page
        page = TaskPage(self, "list", list_id)
        self.stackedWidget.addWidget(page)
        self.list_pages[list_id] = page
        return page

    def _on_page_changed(self, index: int) -> None:
        if self._reverting_page:
            return
        page = self.stackedWidget.widget(index)
        if self.detail.isVisible():
            if self.detail.is_dirty():
                choice = dialogs.ask_save_changes(self)
                if choice == "cancel":
                    self._revert_page()
                    return
                if choice == "save":
                    self.detail.save()
            self.detail.hide()
            self.current_task_id = None
            self._clear_highlights()
        self._last_page_index = index
        if isinstance(page, TaskPage):
            page.refresh()

    def _revert_page(self) -> None:
        self._reverting_page = True
        try:
            self.stackedWidget.setCurrentIndex(self._last_page_index, popOut=False)
        finally:
            self._reverting_page = False

    def _clear_highlights(self) -> None:
        for page in list(self.pages.values()) + list(self.list_pages.values()):
            page.highlight(None)

    def select_view(self, view_type: str) -> None:
        page = self.pages.get(view_type)
        if page is None:
            return
        self.stackedWidget.setCurrentWidget(page, popOut=False)
        self.navigationInterface.setCurrentItem(page.objectName())

    # ================================================== 任务操作

    def quick_add(self, text: str, page: TaskPage) -> None:
        parsed = utils.parse_quick_input(text)
        list_id = page.view_id if page.view_type == "list" else self.db.default_list_id()
        due_date = parsed["due_date"]
        if not due_date:
            # 只写任务名：默认排到今天
            due_date = date.today().isoformat()
        due_time = parsed["due_time"]
        if not due_time:
            # 没写时间：默认 14:00，并且默认到点提醒
            due_time = config.DEFAULT_DUE_CLOCK
        self.db.add_task(
            parsed["title"],
            list_id=list_id,
            due_date=due_date,
            due_time=due_time,
            priority=parsed["priority"],
            remind_offset=0,
            repeat_rule=parsed["repeat"],
        )
        page.refresh()
        self.refresh_counts()

    def toggle_task(self, task_id: int) -> None:
        spawned = self.db.toggle_complete(task_id)
        self.refresh_current()
        if self.current_task_id == task_id and self.detail.isVisible():
            self.detail.load(task_id)
        self._announce_repeat(spawned)

    def open_task(self, task_id: int) -> None:
        if (
            self.detail.isVisible()
            and self.current_task_id != task_id
            and self.detail.is_dirty()
        ):
            choice = dialogs.ask_save_changes(self)
            if choice == "cancel":
                return
            if choice == "save":
                self.detail.save()
        self.current_task_id = task_id
        self.detail.load(task_id)
        self.detail.show()
        page = self.current_page()
        if page:
            page.highlight(task_id)

    def close_detail(self, force: bool = False) -> None:
        if not self.detail.isVisible():
            self.current_task_id = None
            return
        if not force:
            if self.detail.is_dirty():
                choice = dialogs.ask_save_changes(self)
                if choice == "cancel":
                    return
                if choice == "save":
                    self.detail.save()
            else:
                self.detail.status_label.setText("")
        self.detail.hide()
        self.current_task_id = None
        self._clear_highlights()

    def on_task_changed(self, task_id: int) -> None:
        page = self.current_page()
        if page:
            page.refresh()
        self.refresh_counts()

    def delete_task(self, task_id: int) -> None:
        task = self.db.get_task(task_id)
        if task is None:
            return
        if not dialogs.ask_confirm(
            self, "删除任务", f"确定删除「{utils.truncate(task['title'], 26)}」吗？此操作不可撤销。"
        ):
            return
        self.db.delete_task(task_id)
        if self.current_task_id == task_id:
            self.detail.hide()
            self.current_task_id = None
        self.refresh_current()

    # ================================================== 右键菜单

    def task_menu(self, task_id: int, global_pos: QPoint) -> None:
        task = self.db.get_task(task_id)
        if task is None:
            return
        completed = bool(task["completed"])
        menu = RoundMenu(parent=self)
        menu.addAction(
            Action(
                icon=FIF.ACCEPT,
                text="标记为未完成" if completed else "标记完成",
                triggered=lambda: self.toggle_task(task_id),
            )
        )
        menu.addSeparator()

        due_menu = RoundMenu("截止日期", self)
        for text, delta in (("今天", 0), ("明天", 1), ("后天", 2)):
            due_menu.addAction(
                Action(
                    icon=FIF.CALENDAR,
                    text=text,
                    triggered=lambda _=False, d=delta: self._set_due(
                        task_id, (date.today() + timedelta(days=d)).isoformat()
                    ),
                )
            )
        due_menu.addAction(Action(icon=FIF.REMOVE, text="清除日期", triggered=lambda: self._set_due(task_id, None)))
        menu.addMenu(due_menu)

        priority_menu = RoundMenu("优先级", self)
        for level, name in ((3, "高"), (2, "中"), (1, "低"), (0, "无")):
            priority_menu.addAction(
                Action(
                    icon=FIF.FLAG,
                    text=name,
                    triggered=lambda _=False, lv=level: self._set_priority(task_id, lv),
                )
            )
        menu.addMenu(priority_menu)

        if not completed:
            snooze_menu = RoundMenu("稍后提醒", self)
            for label, minutes in config.SNOOZE_OPTIONS:
                snooze_menu.addAction(
                    Action(
                        icon=FIF.STOP_WATCH,
                        text=label,
                        triggered=lambda _=False, m=minutes: self._snooze_task(task_id, m),
                    )
                )
            snooze_menu.addSeparator()
            snooze_menu.addAction(
                Action(
                    icon=FIF.EDIT,
                    text="自定义…",
                    triggered=lambda: self._snooze_custom(task_id),
                )
            )
            menu.addMenu(snooze_menu)

        move_menu = RoundMenu("移动到清单", self)
        for row in self.db.lists():
            move_menu.addAction(
                Action(
                    icon=FIF.FOLDER,
                    text=row["name"],
                    triggered=lambda _=False, lid=int(row["id"]): self._move_task(task_id, lid),
                )
            )
        menu.addMenu(move_menu)

        menu.addSeparator()
        menu.addAction(
            Action(icon=FIF.DELETE, text="删除任务", triggered=lambda: self.delete_task(task_id))
        )
        menu.exec(global_pos)

    def _set_due(self, task_id: int, due_date: str | None) -> None:
        task = self.db.get_task(task_id)
        if task is None:
            return
        self.db.update_task(
            task_id,
            due_date=due_date,
            due_time=task["due_time"] if due_date else None,
            remind_offset=task["remind_offset"] if due_date else None,
        )
        self.refresh_current()
        if self.current_task_id == task_id and self.detail.isVisible():
            self.detail.load(task_id)

    def _set_priority(self, task_id: int, priority: int) -> None:
        self.db.update_task(task_id, priority=priority)
        self.refresh_current()
        if self.current_task_id == task_id and self.detail.isVisible():
            self.detail.load(task_id)

    def _move_task(self, task_id: int, list_id: int) -> None:
        self.db.update_task(task_id, list_id=list_id)
        self.refresh_current()
        if self.current_task_id == task_id and self.detail.isVisible():
            self.detail.load(task_id)

    def _snooze_task(self, task_id: int, minutes: int) -> None:
        self.db.snooze(task_id, minutes)
        self.refresh_current()
        if self.current_task_id == task_id and self.detail.isVisible():
            self.detail.load(task_id)
        if minutes >= 60 and minutes % 60 == 0:
            text = f"{minutes // 60} 小时后提醒"
        else:
            text = f"{minutes} 分钟后提醒"
        self.tray.notify("已推迟提醒", text)

    def _snooze_custom(self, task_id: int) -> None:
        minutes = dialogs.ask_snooze_minutes(self, config.SNOOZE_DEFAULT)
        if minutes:
            self._snooze_task(task_id, minutes)

    # ================================================== 清单管理

    def new_list(self) -> None:
        result = dialogs.ask_list(self, "新建清单")
        if not result:
            return
        name, color = result
        list_id = self.db.add_list(name, color)
        self._rebuild_list_items()
        self.show_list(list_id)

    def edit_list(self, list_id: int) -> None:
        row = next((r for r in self.db.lists() if int(r["id"]) == list_id), None)
        if row is None:
            return
        result = dialogs.ask_list(self, "编辑清单", row["name"], row["color"])
        if not result:
            return
        name, color = result
        self.db.rename_list(list_id, name, color)
        self._rebuild_list_items()
        page = self.list_pages.get(list_id)
        if page and page is self.current_page():
            page.refresh()
            self.navigationInterface.setCurrentItem(f"list_{list_id}")

    def delete_list(self, list_id: int) -> None:
        if len(self.db.lists()) <= 1:
            dialogs.ask_confirm(self, "无法删除", "至少需要保留一个清单。", "知道了")
            return
        row = next((r for r in self.db.lists() if int(r["id"]) == list_id), None)
        name = row["name"] if row else "该清单"
        if not dialogs.ask_confirm(self, "删除清单", f"删除「{name}」后，里面的任务会移动到默认清单。"):
            return
        self.db.delete_list(list_id)
        page = self.list_pages.pop(list_id, None)
        if page is not None:
            self.stackedWidget.removeWidget(page)
            page.deleteLater()
        self._rebuild_list_items()
        self.select_view("today")

    # ================================================== 提醒

    def show_reminder_popup(self, task_id: int) -> None:
        if any(p.task_id == task_id for p in self._popups) or task_id in self._popup_queue:
            return
        task = self.db.get_task(task_id)
        if task is None or task["completed"]:
            return
        if len(self._popups) >= config.POPUP_MAX_VISIBLE:
            # 屏幕上的卡片已经满了，排队等前面的处理完
            self._popup_queue.append(task_id)
            self._sync_popup_queue()
            return
        self._spawn_popup(task)

    def _spawn_popup(self, task) -> None:
        popup = ReminderPopup(
            task,
            index=len(self._popups),
            on_complete=self._popup_complete,
            on_snooze=self._popup_snooze,
            dialog_parent=self,
        )
        popup.closed.connect(self._popup_closed)
        popup.show()
        self._popups.append(popup)
        self._layout_popups()
        self._sync_popup_queue()

    def _popup_closed(self, popup: ReminderPopup) -> None:
        if popup in self._popups:
            self._popups.remove(popup)
        self._layout_popups()
        self._drain_popup_queue()

    def _drain_popup_queue(self) -> None:
        while self._popup_queue and len(self._popups) < config.POPUP_MAX_VISIBLE:
            if self._quitting:
                self._popup_queue.clear()
                break
            task_id = self._popup_queue.pop(0)
            task = self.db.get_task(task_id)
            if task is None or task["completed"]:
                continue
            self._spawn_popup(task)
        self._sync_popup_queue()

    def _sync_popup_queue(self) -> None:
        pending = len(self._popup_queue)
        for index, popup in enumerate(self._popups):
            # 只让最上面那张卡片显示"还有 N 条"
            popup.set_queue_count(pending if index == len(self._popups) - 1 else 0)
        self._layout_popups()

    def _layout_popups(self) -> None:
        if not self._popups:
            return
        area = QGuiApplication.primaryScreen().availableGeometry()
        y = area.bottom() - 4
        for popup in self._popups:
            y -= popup.height()
            popup.move(max(area.left(), area.right() - popup.width() - 8), max(area.top(), y))
            y -= 4

    def _popup_complete(self, task_id: int) -> None:
        spawned = self.db.set_completed(task_id, True)
        self.refresh_current()
        if self.current_task_id == task_id and self.detail.isVisible():
            self.detail.load(task_id)
        self._announce_repeat(spawned)

    def _popup_snooze(self, task_id: int, minutes: int = config.SNOOZE_DEFAULT) -> None:
        self.db.snooze(task_id, minutes)

    def _announce_repeat(self, task_id: int | None) -> None:
        if not task_id:
            return
        task = self.db.get_task(task_id)
        if task is None:
            return
        due = utils.describe_due(task["due_date"], task["due_time"])
        self.tray.notify("循环任务", f"已生成下一次：{due}")

    def show_test_popup(self) -> None:
        task = {
            "id": 0,
            "title": "测试提醒：19:00 和产品过一下需求",
            "due_date": date.today().isoformat(),
            "due_time": datetime.now().strftime("%H:%M"),
            "list_name": "轻待办",
            "list_color": theme.ACCENT,
            "notes": "",
            "repeat_rule": None,
        }
        if len(self._popups) >= config.POPUP_MAX_VISIBLE:
            return
        self._spawn_popup(task)

    def test_notification(self) -> None:
        mode = self.db.get_setting("notify_mode", config.DEFAULTS["notify_mode"])
        sound = self.db.get_setting("notify_sound", "1") == "1"

        if mode in ("toast", "both"):
            # 发通知要起子进程，放到后台线程，避免界面卡住
            threading.Thread(target=self._send_test_toast, name="notify-test", daemon=True).start()
        if mode in ("popup", "both"):
            if sound and mode == "popup":
                sound_alert()
            self.show_test_popup()

    def _send_test_toast(self) -> None:
        ok = self.notifier.show("轻待办 · 测试通知", "如果你看到这条消息，说明系统通知一切正常。")
        if ok:
            return
        detail = self.notifier.last_error or "未知原因"
        self.post(
            lambda: dialogs.ask_confirm(
                self,
                "系统通知发送失败",
                f"{detail}\n可以把提醒方式改成「应用内弹窗」。",
                "知道了",
            )
        )

    def _on_day_change(self, moved: int) -> None:
        self.refresh_all()
        if moved:
            self.tray.notify("新的一天", f"{moved} 项未完成的任务已自动延续到今天。")

    # ================================================== 设置

    def set_topmost(self, value: bool) -> None:
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, value)
        if visible:
            self.show()

    def sync_autostart_state(self) -> None:
        enabled = autostart.is_enabled()
        self.tray.set_autostart(enabled)
        self.db.set_setting("autostart", "1" if enabled else "0")

    def toggle_autostart(self) -> None:
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()
        self.sync_autostart_state()
        try:
            self.settings_page.sync()
        except Exception:
            pass

    def clear_completed(self) -> None:
        if not dialogs.ask_confirm(self, "清空已完成", "将永久删除所有已完成的任务，确定继续吗？"):
            return
        removed = self.db.clear_completed()
        self.refresh_all()
        self.tray.notify("已清理", f"删除了 {removed} 条已完成任务")

    # ================================================== 窗口

    def new_task(self) -> None:
        self.show_window()
        page = self.current_page()
        if page is None or page.view_type == "completed":
            self.select_view("today")
            page = self.current_page()
        if page:
            page.focus_input()

    def show_window(self) -> None:
        self.showNormal()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.raise_()
        self.activateWindow()

    def _save_geometry(self) -> None:
        try:
            data = bytes(self.saveGeometry())
            self.db.set_setting("window_geometry", data.hex())
        except Exception:
            pass

    def _restore_geometry(self) -> None:
        saved = self.db.get_setting("window_geometry", "")
        if not saved:
            return
        try:
            self.restoreGeometry(QByteArray.fromHex(bytes.fromhex(saved)))
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        if self._quitting:
            event.accept()
            return
        if self.db.get_setting("close_to_tray", "1") == "1":
            event.ignore()
            self._save_geometry()
            self.hide()
            if self.db.get_setting("tray_hint_shown", "0") != "1":
                self.db.set_setting("tray_hint_shown", "1")
                self.tray.notify("轻待办仍在后台运行", "提醒照常，双击托盘图标可以重新打开。")
        else:
            event.accept()
            self.quit_app()

    def quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        try:
            if self.detail.isVisible() and self.detail.is_dirty():
                self.detail.save()
        except Exception:
            log.exception("保存未提交的编辑失败")
        self._save_geometry()
        try:
            self._pump_timer.stop()
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
        for popup in list(self._popups):
            try:
                popup.close()
            except Exception:
                pass
        try:
            self.db.close()
        except Exception:
            pass
        QApplication.instance().quit()

    # ================================================== 跨线程

    def post(self, func) -> None:
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
