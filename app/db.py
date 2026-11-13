"""SQLite 数据层：任务、清单、设置、自动延期、提醒查询。"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config, utils

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#3A6FF7',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id       INTEGER,
    title         TEXT NOT NULL,
    notes         TEXT NOT NULL DEFAULT '',
    due_date      TEXT,
    due_time      TEXT,
    remind_offset INTEGER,
    remind_at     TEXT,
    reminded      INTEGER NOT NULL DEFAULT 0,
    priority      INTEGER NOT NULL DEFAULT 0,
    completed     INTEGER NOT NULL DEFAULT 0,
    completed_at  TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    defer_count   INTEGER NOT NULL DEFAULT 0,
    orig_due_date TEXT,
    repeat_rule   TEXT,
    FOREIGN KEY (list_id) REFERENCES lists (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_due    ON tasks (completed, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_remind ON tasks (reminded, remind_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_LIST_NAME = "收集箱"
DEFAULT_LIST_COLOR = "#3A6FF7"


# ---------------------------------------------------------------- 时间工具


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return date.today().isoformat()


def compute_remind_at(due_date: str | None, due_time: str | None, offset: int | None) -> str | None:
    """根据截止时间与提前量算出提醒时刻（没写时间按 15:00）。"""
    if not due_date or offset is None:
        return None
    clock = due_time or config.DEFAULT_DUE_CLOCK
    try:
        dt = datetime.strptime(f"{due_date} {clock}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    dt -= timedelta(minutes=int(offset))
    return dt.strftime("%Y-%m-%d %H:%M")


def parse_due_date(value: str | None) -> str | None:
    """把用户输入规整成 YYYY-MM-DD，无法识别返回 None。"""
    if not value:
        return None
    value = value.strip().replace("/", "-").replace(".", "-")
    if value in ("今天", "今日"):
        return date.today().isoformat()
    if value in ("明天", "明日"):
        return (date.today() + timedelta(days=1)).isoformat()
    if value in ("后天",):
        return (date.today() + timedelta(days=2)).isoformat()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%m-%d":
                dt = dt.replace(year=date.today().year)
            return dt.date().isoformat()
        except ValueError:
            continue
    return None


def parse_due_time(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().replace("：", ":").replace(".", ":")
    for fmt in ("%H:%M", "%H%M", "%H"):
        try:
            return datetime.strptime(value, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- 数据库


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()
        self._ensure_defaults()

    # -------------------------------------------------- 初始化

    def _migrate(self) -> None:
        with self._lock:
            self.conn.executescript(SCHEMA)
            columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(tasks)")}
            if "repeat_rule" not in columns:
                self.conn.execute("ALTER TABLE tasks ADD COLUMN repeat_rule TEXT")
            self.conn.commit()

    def _ensure_defaults(self) -> None:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) AS c FROM lists").fetchone()
            if row["c"] == 0:
                self.conn.execute(
                    "INSERT INTO lists (name, color, sort_order, created_at) VALUES (?, ?, ?, ?)",
                    (DEFAULT_LIST_NAME, DEFAULT_LIST_COLOR, 0, now_str()),
                )
                self.conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.commit()
                self.conn.close()
            except Exception:
                pass

    # -------------------------------------------------- 设置

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
            self.conn.commit()

    # -------------------------------------------------- 清单

    def lists(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM lists ORDER BY sort_order ASC, id ASC"
            ).fetchall()

    def default_list_id(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT id FROM lists ORDER BY sort_order ASC, id ASC LIMIT 1").fetchone()
        return int(row["id"]) if row else 1

    def add_list(self, name: str, color: str) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO lists (name, color, sort_order, created_at) VALUES (?, ?, ?, ?)",
                (name.strip(), color, int(datetime.now().timestamp()), now_str()),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def rename_list(self, list_id: int, name: str, color: str | None = None) -> None:
        with self._lock:
            if color:
                self.conn.execute("UPDATE lists SET name = ?, color = ? WHERE id = ?", (name.strip(), color, list_id))
            else:
                self.conn.execute("UPDATE lists SET name = ? WHERE id = ?", (name.strip(), list_id))
            self.conn.commit()

    def delete_list(self, list_id: int) -> None:
        """删除清单，里面的任务移动到默认清单。"""
        with self._lock:
            target = self.default_list_id()
            if target == list_id:
                others = [r for r in self.lists() if r["id"] != list_id]
                if not others:
                    return
                target = int(others[0]["id"])
            self.conn.execute("UPDATE tasks SET list_id = ? WHERE list_id = ?", (target, list_id))
            self.conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
            self.conn.commit()

    # -------------------------------------------------- 任务

    def add_task(
        self,
        title: str,
        list_id: int | None = None,
        due_date: str | None = None,
        due_time: str | None = None,
        notes: str = "",
        priority: int = 0,
        remind_offset: int | None = 0,
        repeat_rule: str | None = None,
    ) -> int:
        title = (title or "").strip()
        if not title:
            raise ValueError("任务标题不能为空")
        if list_id is None:
            list_id = self.default_list_id()
        remind_at = compute_remind_at(due_date, due_time, remind_offset)
        # 建任务时点已经过去的提醒不再补弹（比如下午补记上午的事）
        reminded = 0
        if remind_at and remind_at <= datetime.now().strftime("%Y-%m-%d %H:%M"):
            reminded = 1
        stamp = now_str()
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO tasks (list_id, title, notes, due_date, due_time, remind_offset, remind_at,"
                " reminded, priority, completed, created_at, updated_at, repeat_rule)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
                (list_id, title, notes, due_date, due_time, remind_offset, remind_at,
                 reminded, priority, stamp, stamp, repeat_rule or None),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def update_task(self, task_id: int, **fields) -> None:
        allowed = {
            "title",
            "notes",
            "list_id",
            "due_date",
            "due_time",
            "remind_offset",
            "priority",
            "completed",
            "repeat_rule",
        }
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return
        with self._lock:
            row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return

            merged = dict(row)
            merged.update(data)
            remind_at = compute_remind_at(merged["due_date"], merged["due_time"], merged["remind_offset"])
            reminded = row["reminded"]
            if remind_at != row["remind_at"]:
                if remind_at and remind_at > datetime.now().strftime("%Y-%m-%d %H:%M"):
                    reminded = 0
                elif remind_at:
                    reminded = 1
                else:
                    reminded = 0

            if merged["title"] is not None:
                merged["title"] = str(merged["title"]).strip() or row["title"]

            self.conn.execute(
                "UPDATE tasks SET title = ?, notes = ?, list_id = ?, due_date = ?, due_time = ?,"
                " remind_offset = ?, remind_at = ?, reminded = ?, priority = ?, repeat_rule = ?,"
                " updated_at = ? WHERE id = ?",
                (
                    merged["title"],
                    merged["notes"] or "",
                    merged["list_id"],
                    merged["due_date"],
                    merged["due_time"],
                    merged["remind_offset"],
                    remind_at,
                    reminded,
                    int(merged["priority"] or 0),
                    merged.get("repeat_rule") or None,
                    now_str(),
                    task_id,
                ),
            )
            self.conn.commit()

    def get_task(self, task_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                "SELECT t.*, l.name AS list_name, l.color AS list_color"
                " FROM tasks t LEFT JOIN lists l ON l.id = t.list_id WHERE t.id = ?",
                (task_id,),
            ).fetchone()

    def delete_task(self, task_id: int) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self.conn.commit()

    def _spawn_repeat_next(self, row) -> int | None:
        """完成循环任务时生成下一次的副本，返回新任务 id。需在锁内调用。"""
        rule = row["repeat_rule"]
        if not rule:
            return None
        base = date.fromisoformat(row["due_date"]) if row["due_date"] else date.today()
        next_day = utils.next_repeat_date(rule, base)
        today = date.today()
        # 补做很久以前的任务时，把下一次推到「今天或以后」，避免生成一堆过去的任务
        guard = 0
        while next_day < today and guard < 500:
            next_day = utils.next_repeat_date(rule, next_day)
            guard += 1
        # 「每天 / 工作日 / 每 N 天」这类习惯型循环：补做昨天（或更早）的任务时，
        # 今天这一次仍要保留，不能因为今天的时间点已过就跳到明天，否则今天就“没任务”了。
        kind, _, rest = rule.partition(":")
        daily_like = kind in ("daily", "weekdays") or (kind == "interval" and rest.endswith(":day"))
        if next_day == today and row["due_time"] and not daily_like:
            if row["due_time"] <= datetime.now().strftime("%H:%M"):
                next_day = utils.next_repeat_date(rule, next_day)
        next_date = next_day.isoformat()
        remind_at = compute_remind_at(next_date, row["due_time"], row["remind_offset"])
        reminded = 1 if remind_at and remind_at <= datetime.now().strftime("%Y-%m-%d %H:%M") else 0
        stamp = now_str()
        cur = self.conn.execute(
            "INSERT INTO tasks (list_id, title, notes, due_date, due_time, remind_offset, remind_at,"
            " reminded, priority, completed, created_at, updated_at, repeat_rule)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (
                row["list_id"],
                row["title"],
                row["notes"] or "",
                next_date,
                row["due_time"],
                row["remind_offset"],
                remind_at,
                reminded,
                int(row["priority"] or 0),
                stamp,
                stamp,
                rule,
            ),
        )
        return int(cur.lastrowid)

    def toggle_complete(self, task_id: int) -> int | None:
        """切换完成状态；若是循环任务并标记完成，会生成下一次，返回新任务 id。"""
        with self._lock:
            row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return None
            done = 0 if row["completed"] else 1
            reminded = row["reminded"]
            if not done:
                remind_at = row["remind_at"]
                reminded = 0 if remind_at and remind_at > datetime.now().strftime("%Y-%m-%d %H:%M") else 1
            self.conn.execute(
                "UPDATE tasks SET completed = ?, completed_at = ?, reminded = ?, updated_at = ? WHERE id = ?",
                (done, now_str() if done else None, reminded, now_str(), task_id),
            )
            spawned = self._spawn_repeat_next(row) if done else None
            self.conn.commit()
            return spawned

    def set_completed(self, task_id: int, done: bool) -> int | None:
        """设置完成状态；循环任务完成时生成下一次，返回新任务 id。"""
        with self._lock:
            row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return None
            self.conn.execute(
                "UPDATE tasks SET completed = ?, completed_at = ?, updated_at = ? WHERE id = ?",
                (1 if done else 0, now_str() if done else None, now_str(), task_id),
            )
            spawned = None
            if done and not row["completed"]:
                spawned = self._spawn_repeat_next(row)
            self.conn.commit()
            return spawned

    # -------------------------------------------------- 查询

    def tasks_for_view(
        self,
        view_type: str,
        view_id: int | None = None,
        search: str = "",
        show_completed: bool = False,
    ) -> list[sqlite3.Row]:
        today = today_str()
        where: list[str] = []
        params: list = []

        if view_type == "inbox":
            where.append("t.due_date IS NULL")
        elif view_type == "today":
            where.append("t.due_date IS NOT NULL AND t.due_date <= ?")
            params.append(today)
        elif view_type == "next7":
            end = (date.today() + timedelta(days=6)).isoformat()
            where.append("t.due_date IS NOT NULL AND t.due_date BETWEEN ? AND ?")
            params.extend([today, end])
        elif view_type == "list":
            where.append("t.list_id = ?")
            params.append(view_id)
        elif view_type == "completed":
            where.append("t.completed = 1")
        elif view_type == "search":
            pass
        # "all" 不加条件

        if view_type != "completed" and not show_completed:
            where.append("t.completed = 0")
        if view_type == "completed":
            where.append("t.completed = 1")

        if search:
            like = f"%{search.strip()}%"
            where.append("(t.title LIKE ? OR t.notes LIKE ?)")
            params.extend([like, like])

        sql = (
            "SELECT t.*, l.name AS list_name, l.color AS list_color"
            " FROM tasks t LEFT JOIN lists l ON l.id = t.list_id"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        if view_type == "completed":
            sql += " ORDER BY t.completed_at DESC, t.id DESC LIMIT 500"
        else:
            sql += (
                " ORDER BY t.completed ASC, (t.due_date IS NULL) ASC, t.due_date ASC,"
                " COALESCE(t.due_time, '99:99') ASC, t.priority DESC, t.id DESC"
            )
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def counts(self) -> dict:
        today = today_str()
        end7 = (date.today() + timedelta(days=6)).isoformat()
        with self._lock:
            def one(sql: str, params: tuple = ()) -> int:
                return int(self.conn.execute(sql, params).fetchone()[0])

            result = {
                "today": one(
                    "SELECT COUNT(*) FROM tasks WHERE completed = 0 AND due_date IS NOT NULL AND due_date <= ?",
                    (today,),
                ),
                "next7": one(
                    "SELECT COUNT(*) FROM tasks WHERE completed = 0 AND due_date IS NOT NULL"
                    " AND due_date BETWEEN ? AND ?",
                    (today, end7),
                ),
                "all": one("SELECT COUNT(*) FROM tasks WHERE completed = 0"),
                "inbox": one("SELECT COUNT(*) FROM tasks WHERE completed = 0 AND due_date IS NULL"),
                "completed": one("SELECT COUNT(*) FROM tasks WHERE completed = 1"),
                "lists": {},
            }
            for row in self.conn.execute(
                "SELECT list_id, COUNT(*) AS c FROM tasks WHERE completed = 0 GROUP BY list_id"
            ):
                result["lists"][row["list_id"]] = int(row["c"])
            return result

    def overdue_count(self) -> int:
        with self._lock:
            return int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE completed = 0 AND due_date IS NOT NULL AND due_date < ?",
                    (today_str(),),
                ).fetchone()[0]
            )

    # -------------------------------------------------- 自动延期 / 提醒

    def rollover(self) -> int:
        """把已过期未完成的任务顺延到今天（即"延续到下一天"），返回处理条数。"""
        today = today_str()
        now_str_value = datetime.now().strftime("%Y-%m-%d %H:%M")
        moved = 0
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, due_date, due_time, remind_offset FROM tasks"
                " WHERE completed = 0 AND due_date IS NOT NULL AND due_date < ?",
                (today,),
            ).fetchall()
            for row in rows:
                remind_at = compute_remind_at(today, row["due_time"], row["remind_offset"])
                if remind_at is None:
                    reminded = 0
                else:
                    reminded = 0 if remind_at > now_str_value else 1
                self.conn.execute(
                    "UPDATE tasks SET due_date = ?, defer_count = defer_count + 1,"
                    " orig_due_date = COALESCE(orig_due_date, due_date),"
                    " remind_at = ?, reminded = ?, updated_at = ? WHERE id = ?",
                    (today, remind_at, reminded, now_str(), row["id"]),
                )
                moved += 1
            if moved:
                self.conn.commit()
        return moved

    def due_reminders(self, at: datetime | None = None) -> list[sqlite3.Row]:
        moment = (at or datetime.now()).strftime("%Y-%m-%d %H:%M")
        with self._lock:
            return self.conn.execute(
                "SELECT t.*, l.name AS list_name, l.color AS list_color"
                " FROM tasks t LEFT JOIN lists l ON l.id = t.list_id"
                " WHERE t.completed = 0 AND t.remind_at IS NOT NULL AND t.reminded = 0 AND t.remind_at <= ?"
                " ORDER BY t.remind_at ASC LIMIT 10",
                (moment,),
            ).fetchall()

    def mark_reminded(self, task_id: int) -> None:
        with self._lock:
            self.conn.execute("UPDATE tasks SET reminded = 1 WHERE id = ?", (task_id,))
            self.conn.commit()

    def snooze(self, task_id: int, minutes: int = 10) -> None:
        """稍后提醒：把提醒时间推后若干分钟并重新置为未提醒。"""
        moment = datetime.now() + timedelta(minutes=int(minutes))
        with self._lock:
            self.conn.execute(
                "UPDATE tasks SET remind_at = ?, reminded = 0, updated_at = ? WHERE id = ?",
                (moment.strftime("%Y-%m-%d %H:%M"), now_str(), task_id),
            )
            self.conn.commit()

    def clear_completed(self) -> int:
        with self._lock:
            cur = self.conn.execute("DELETE FROM tasks WHERE completed = 1")
            self.conn.commit()
            return cur.rowcount

    def has_any_task(self) -> bool:
        with self._lock:
            return bool(self.conn.execute("SELECT 1 FROM tasks LIMIT 1").fetchone())
