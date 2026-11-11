"""通用小工具：日期文案、文本解析等。"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def today() -> date:
    return date.today()


def human_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return value
    delta = (d - date.today()).days
    if delta == 0:
        return "今天"
    if delta == 1:
        return "明天"
    if delta == 2:
        return "后天"
    if delta == -1:
        return "昨天"
    if -7 < delta < 0:
        return f"逾期 {-delta} 天"
    if 2 < delta < 7:
        return WEEKDAYS[d.weekday()]
    if d.year == date.today().year:
        return f"{d.month}月{d.day}日"
    return f"{d.year}年{d.month}月{d.day}日"


def describe_due(due_date: str | None, due_time: str | None) -> str:
    if not due_date:
        return "无日期"
    text = human_date(due_date)
    if due_time:
        text = f"{text} {due_time}"
    return text


def is_overdue(due_date: str | None, due_time: str | None) -> bool:
    if not due_date:
        return False
    stamp = f"{due_date} {due_time or '23:59'}"
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%M") < datetime.now()
    except ValueError:
        return False


# ---------------------------------------------------------------- 智能解析

CN_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
CN_CHARS = "零〇一二两三四五六七八九十"

PERIODS = (
    "凌晨", "清晨", "早上", "早晨", "上午", "中午",
    "下午", "傍晚", "晚上", "夜里", "今晚", "明晚", "明早",
)

_HOUR = rf"(?:[0-9]{{1,2}}|[{CN_CHARS}]{{1,3}})"
_MINUTE = rf"(?:[0-9]{{2}}|[{CN_CHARS}]{{1,3}})"

TIME_RE = re.compile(
    rf"(?P<period>{'|'.join(PERIODS)})?\s*(?<![0-9])"
    rf"(?P<hour>{_HOUR})\s*(?P<sep>[:：点时時])\s*"
    rf"(?:(?P<minute>{_MINUTE})(?!刻)\s*分?)?"
    rf"(?P<half>半)?(?P<quarter>一刻|三刻)?"
)

PRIORITY_RE = re.compile(r"(!{1,3})")

RELATIVE_DAYS = (
    ("大后天", 3), ("后天", 2), ("明天", 1), ("明日", 1), ("今天", 0), ("今日", 0),
)

WEEKDAY_RE = re.compile(r"(?P<next>下)?\s*(?:周|星期|礼拜)\s*(?P<w>[一二三四五六日天])")
WEEKDAY_INDEX = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

DATE_FULL_RE = re.compile(
    r"(?<!\d)(?P<y>\d{4})\s*[-/.年]\s*(?P<m>\d{1,2})\s*[-/.月]\s*(?P<d>\d{1,2})\s*[日号]?(?!\d)"
)
DATE_MD_RE = re.compile(r"(?<!\d)(?P<m>\d{1,2})\s*[-/.月]\s*(?P<d>\d{1,2})\s*[日号]?(?!\d)")

# 相对时间：1分钟后 / 半小时后 / 两小时之后 / 3天后
RELATIVE_UNITS: list[tuple[str, int]] = [
    ("秒钟", 1),
    ("秒", 1),
    ("分钟", 60),
    ("分", 60),
    ("小时", 3600),
    ("钟头", 3600),
    ("星期", 604800),
    ("礼拜", 604800),
    ("周", 604800),
    ("天", 86400),
    ("日", 86400),
]
_RELATIVE_UNIT_MAP = dict(RELATIVE_UNITS)

RELATIVE_RE = re.compile(
    rf"(?<![0-9])"
    rf"(?P<num>[0-9]{{1,3}}|[{CN_CHARS}]{{1,3}}|半)\s*个?\s*"
    rf"(?P<unit>{'|'.join(unit for unit, _ in RELATIVE_UNITS)})\s*"
    rf"(?:之?后|以后|过后)"
)

# 循环：每天 / 每周三 / 每三天 / 每两周
REPEAT_RE = re.compile(
    r"每\s*(?P<num>[0-9]{1,2}|[一二两三四五六七八九十]{1,2})?\s*个?\s*"
    r"(?P<unit>天|日|周|星期|礼拜|月)"
    r"(?:\s*(?P<dom>[0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*[日号])?"
    r"\s*(?P<wd>[一二三四五六日天])?"
)


def cn_number(text: str | None) -> int | None:
    """中文数字转 int：「十」→10，「十一」→11，「二十三」→23，「两」→2。"""
    text = (text or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if "十" in text:
        left, _, right = text.partition("十")
        if left and left not in CN_DIGITS:
            return None
        tens = CN_DIGITS[left] if left else 1
        if right and right not in CN_DIGITS:
            return None
        ones = CN_DIGITS[right] if right else 0
        return tens * 10 + ones
    total = 0
    for ch in text:
        if ch not in CN_DIGITS:
            return None
        total = total * 10 + CN_DIGITS[ch]
    return total


def _cut(text: str, start: int, end: int) -> str:
    return (text[:start] + " " + text[end:]).strip()


def _extract_time(text: str) -> tuple[str | None, str | None, str]:
    """返回 (HH:MM, 时段词, 剩余文本)。"""
    match = TIME_RE.search(text)
    if not match:
        return None, None, text

    hour = cn_number(match.group("hour"))
    minute = cn_number(match.group("minute")) if match.group("minute") else 0
    if hour is None:
        return None, None, text
    if match.group("half"):
        minute = 30
    elif match.group("quarter") == "一刻":
        minute = 15
    elif match.group("quarter") == "三刻":
        minute = 45
    minute = minute or 0

    period = match.group("period")
    if period in ("下午", "傍晚") and hour < 12:
        hour += 12
    elif period in ("晚上", "夜里", "今晚", "明晚") and hour < 12:
        hour += 12
    elif period == "中午" and hour <= 2:
        hour += 12
    elif period in ("凌晨", "清晨") and hour == 12:
        hour = 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None, None, text

    return f"{hour:02d}:{minute:02d}", period, _cut(text, match.start(), match.end())


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_date(text: str, period: str | None) -> tuple[str | None, str]:
    if period in ("今晚", "明早", "明晚"):
        offset = 1 if period in ("明早", "明晚") else 0
        result = (date.today() + timedelta(days=offset)).isoformat()
        # 时段词已被时间解析吃掉，这里不再裁剪文本
        return result, text

    for word, offset in RELATIVE_DAYS:
        if word in text:
            index = text.index(word)
            return (
                (date.today() + timedelta(days=offset)).isoformat(),
                _cut(text, index, index + len(word)),
            )

    match = WEEKDAY_RE.search(text)
    if match:
        target = WEEKDAY_INDEX[match.group("w")]
        today_index = date.today().weekday()
        if match.group("next"):
            delta = 7 - today_index + target
        else:
            delta = (target - today_index) % 7
        return (date.today() + timedelta(days=delta)).isoformat(), _cut(text, match.start(), match.end())

    match = DATE_FULL_RE.search(text)
    if match:
        target = _safe_date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
        if target:
            return target.isoformat(), _cut(text, match.start(), match.end())

    match = DATE_MD_RE.search(text)
    if match:
        month, day = int(match.group("m")), int(match.group("d"))
        target = _safe_date(date.today().year, month, day)
        if target and target < date.today():
            target = _safe_date(date.today().year + 1, month, day)
        if target:
            return target.isoformat(), _cut(text, match.start(), match.end())

    return None, text


def _extract_repeat(text: str) -> tuple[str | None, int | None, str]:
    """识别「每天 / 每周三 / 每三天 / 每月 15 号」。

    返回 (规则, 星期索引或 None, 剩余文本)。
    规则形如 daily / weekly / weekly:2 / monthly:15 / interval:3:day。
    """
    match = REPEAT_RE.search(text)
    if not match:
        return None, None, text

    unit = match.group("unit")
    num_text = match.group("num")
    dom_text = match.group("dom")
    weekday_char = match.group("wd")
    weekday = WEEKDAY_INDEX.get(weekday_char) if weekday_char else None

    if unit == "月":
        day = cn_number(dom_text) if dom_text else None
        rule = f"monthly:{day}" if day else "monthly"
    elif unit in ("周", "星期", "礼拜"):
        value = cn_number(num_text) if num_text else 1
        value = value or 1
        rule = ("weekly" if value == 1 else f"interval:{value}:week")
    else:  # 天 / 日
        value = cn_number(num_text) if num_text else 1
        value = value or 1
        rule = "daily" if value == 1 else f"interval:{value}:day"

    if weekday is not None and rule == "weekly":
        rule = f"weekly:{weekday}"

    return rule, weekday, _cut(text, match.start(), match.end())


def repeat_label(rule: str | None) -> str:
    """规则转可读文案：daily→每天，interval:3:day→每 3 天，weekly:2→每周三。"""
    rule = (rule or "").strip()
    if not rule:
        return ""
    kind, _, rest = rule.partition(":")
    if kind == "daily":
        return "每天"
    if kind == "weekdays":
        return "工作日"
    if kind == "monthly":
        if rest.isdigit():
            return f"每月 {int(rest)} 号"
        return "每月"
    if kind == "weekly":
        if rest.isdigit() and int(rest) < 7:
            return f"每周{'一二三四五六日'[int(rest)]}"
        return "每周"
    if kind == "interval":
        num, _, unit = rest.partition(":")
        unit_text = "周" if unit.startswith("week") else "天"
        return f"每 {num} {unit_text}"
    return ""


def _add_month(value: date) -> date:
    month = value.month + 1
    year = value.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(value.day, last_day))


def _next_month_day(base: date, day: int) -> date:
    year, month = base.year, base.month
    for _ in range(24):
        month += 1
        if month > 12:
            month = 1
            year += 1
        if day <= calendar.monthrange(year, month)[1]:
            return date(year, month, day)
    return _add_month(base)


def next_repeat_date(rule: str | None, base: date) -> date:
    """按循环规则算出下一次日期。"""
    kind, _, rest = (rule or "").partition(":")
    if kind == "daily":
        return base + timedelta(days=1)
    if kind == "weekdays":
        nxt = base + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        return nxt
    if kind == "weekly":
        # 带星期几的规则（weekly:2）要对齐到那一天，避免日期漂移
        target = int(rest) if rest.isdigit() and int(rest) < 7 else base.weekday()
        delta = (target - base.weekday()) % 7
        return base + timedelta(days=delta or 7)
    if kind == "monthly":
        if rest.isdigit():
            return _next_month_day(base, int(rest))
        return _add_month(base)
    if kind == "interval":
        num, _, unit = rest.partition(":")
        try:
            step = max(1, int(num))
        except ValueError:
            step = 1
        return base + timedelta(days=step * (7 if unit.startswith("week") else 1))
    return base + timedelta(days=1)


def repeat_anchor(rule: str | None, today: date) -> date:
    """循环任务第一次该落在哪天（没写日期时用）。"""
    kind, _, rest = (rule or "").partition(":")
    if kind == "monthly" and rest.isdigit():
        day = int(rest)
        if day >= today.day and day <= calendar.monthrange(today.year, today.month)[1]:
            return today.replace(day=day)
        return _next_month_day(today, day)
    return today


def _extract_relative(text: str) -> tuple[str | None, str | None, str, str]:
    """识别「1 分钟后」「半小时后」「两小时之后」。

    返回 (YYYY-MM-DD, HH:MM, 剩余文本, 可读标签)。
    """
    match = RELATIVE_RE.search(text)
    if not match:
        return None, None, text, ""

    num_text = match.group("num")
    unit = match.group("unit")
    seconds_per_unit = _RELATIVE_UNIT_MAP.get(unit, 0)
    if not seconds_per_unit:
        return None, None, text, ""

    if num_text == "半":
        value: float = 0.5
    else:
        value = float(cn_number(num_text) or 0)
    if value <= 0:
        return None, None, text, ""

    minutes = max(1, round(value * seconds_per_unit / 60))
    target = (datetime.now() + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    if num_text == "半":
        label = f"半{unit}后"
    elif num_text.isdigit():
        label = f"{num_text} {unit}后"
    else:
        label = f"{num_text}{unit}后"
    return (
        target.date().isoformat(),
        target.strftime("%H:%M"),
        _cut(text, match.start(), match.end()),
        label,
    )


def parse_quick_input(text: str) -> dict:
    """从一句话里识别标题、截止日期、时间、优先级。

    支持示例：
        交周报 明天 18:00 !!
        十点开会 / 十点半打电话 / 十一点30 见客户
        下午三点 评审 / 明早八点 跑步 / 周五晚上8点 聚餐
        11月20日 15:00 交付
        1小时后 回电话 / 半小时后 出门 / 3天后 复盘
    """
    raw = (text or "").strip()
    result: dict = {
        "title": raw, "due_date": None, "due_time": None,
        "priority": 0, "matched": "", "relative": "",
        "repeat": None, "repeat_label": "",
    }
    if not raw:
        return result

    working = raw

    match = PRIORITY_RE.search(working)
    if match:
        result["priority"] = len(match.group(1))
        working = _cut(working, match.start(), match.end())

    # 循环规则（每天 / 每周三 / 每三天）先剥掉，免得干扰日期解析
    repeat_rule, repeat_weekday, working = _extract_repeat(working)
    result["repeat"] = repeat_rule
    result["repeat_label"] = repeat_label(repeat_rule)

    # 相对时间优先：它同时决定了日期和时间
    rel_date, rel_time, working, rel_label = _extract_relative(working)
    if rel_date:
        result["due_date"] = rel_date
        result["due_time"] = rel_time
        result["relative"] = rel_label
    else:
        due_time, period, working = _extract_time(working)
        result["due_time"] = due_time
        result["due_date"], working = _extract_date(working, period)

    title = re.sub(r"\s{2,}", " ", working).strip(" ，,、;；:：-")
    result["title"] = title or raw

    # 「每周三」这种：用星期几定位第一次
    if repeat_weekday is not None and not result["due_date"]:
        delta = (repeat_weekday - date.today().weekday()) % 7
        if delta == 0 and result["due_time"]:
            hour, minute = (int(x) for x in result["due_time"].split(":"))
            now = datetime.now()
            if (hour, minute) <= (now.hour, now.minute):
                delta = 7
        result["due_date"] = (date.today() + timedelta(days=delta)).isoformat()

    # 循环任务至少要有日期；「每月 15 号」这类按日号定位
    if repeat_rule and not result["due_date"]:
        result["due_date"] = repeat_anchor(repeat_rule, date.today()).isoformat()

    # 只写了时间：今天还没到就排在今天，已经过了就排到明天
    if result["due_time"] and not result["due_date"]:
        now = datetime.now()
        hour, minute = (int(x) for x in result["due_time"].split(":"))
        target = now.date() if (hour, minute) > (now.hour, now.minute) else now.date() + timedelta(days=1)
        result["due_date"] = target.isoformat()

    # 循环任务第一次的时间已经过了，就顺延到下一次
    if repeat_rule and result["due_date"] and result["due_time"]:
        try:
            first = datetime.strptime(f"{result['due_date']} {result['due_time']}", "%Y-%m-%d %H:%M")
            if first <= datetime.now():
                result["due_date"] = next_repeat_date(repeat_rule, first.date()).isoformat()
        except ValueError:
            pass

    parts = []
    if result["relative"]:
        parts.append(result["relative"])
    if result["due_date"]:
        parts.append(human_date(result["due_date"]))
    if result["due_time"]:
        parts.append(result["due_time"])
    result["matched"] = (" · ".join(parts) if result["relative"] else " ".join(parts)).strip()

    summary = " · ".join(part for part in (result["matched"], result["repeat_label"]) if part)
    result["summary"] = summary
    return result


def truncate(text: str, limit: int) -> str:
    text = (text or "").replace("\n", " ")
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def fmt_created(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
