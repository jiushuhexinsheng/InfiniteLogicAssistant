# -*- coding: utf-8 -*-
"""定时任务 — cron（5 段：分 时 日 月 周）注册，到点触发 on_fire(prompt)
Scheduler — registers cron jobs (5 fields: minute hour day month weekday) and fires on_fire(prompt) when due.

持久化到 data/schedules.json；同分钟去重触发。
Persisted to data/schedules.json; firing is deduplicated within the same minute.
"""
import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from core.config import ROOT_DIR

SCHEDULES_FILE = ROOT_DIR / "data" / "schedules.json"


@dataclass
class Schedule:
    """一条定时任务记录（id、cron 表达式、prompt、是否启用）。
    A scheduled job record (id, cron expression, prompt, enabled flag)."""

    id: str
    cron: str
    prompt: str
    enabled: bool = True


def _match(field: str, value: int) -> bool:
    """cron 字段匹配：* / 列表 a,b / 范围 a-b / 步长 */n 与 a-b/n / 精确值
    Matches a cron field: * / list a,b / range a-b / step */n and a-b/n / exact value."""
    field = field.strip()
    if field == "*":
        return True
    # 列表：任意一项匹配即匹配
    if "," in field:
        return any(_match(part, value) for part in field.split(","))
    # 步长：*/n 或 a-b/n
    if "/" in field:
        base, _, step_s = field.partition("/")
        try:
            step = int(step_s)
        except ValueError:
            return False
        if step <= 0:
            return False
        if base == "*":
            return value % step == 0
        if "-" in base:
            a_s, _, b_s = base.partition("-")
            try:
                a, b = int(a_s), int(b_s)
            except ValueError:
                return False
            return a <= value <= b and (value - a) % step == 0
        return False
    # 范围：a-b（含端点）
    if "-" in field:
        a_s, _, b_s = field.partition("-")
        try:
            a, b = int(a_s), int(b_s)
        except ValueError:
            return False
        return a <= value <= b
    try:
        return value == int(field)
    except ValueError:
        return False


def cron_matches(cron: str, now: datetime) -> bool:
    """判断给定时间是否匹配 5 段 cron 表达式（分钟级精度）。
    Checks whether the given time matches a 5-field cron expression (minute resolution)."""
    parts = cron.split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    return (
        _match(minute, now.minute)
        and _match(hour, now.hour)
        and _match(dom, now.day)
        and _match(month, now.month)
        and _match(dow, now.isoweekday() % 7)
    )


class Scheduler:
    """定时调度器：注册 cron 任务、到点异步触发回调，并持久化到 JSON 文件。
    Scheduler: registers cron jobs, fires an async callback when due, and persists jobs to a JSON file."""

    def __init__(self, path: Path = SCHEDULES_FILE, on_fire=None):
        """构造器：记录持久化路径并加载既有任务。Constructor: records the persistence path and loads existing jobs."""
        self.path = path
        self._schedules: dict[str, Schedule] = {}
        self._last_fire: dict[str, str] = {}
        self._on_fire = on_fire  # async (prompt) -> None
        self._running = False
        self._task: asyncio.Task | None = None
        self._load()

    def add(self, cron: str, prompt: str) -> Schedule:
        """注册一条新定时任务并持久化，返回生成的 Schedule。
        Registers a new scheduled job, persists it, and returns the created Schedule."""
        sc = Schedule(id=uuid.uuid4().hex[:8], cron=cron, prompt=prompt)
        self._schedules[sc.id] = sc
        self._save()
        return sc

    def remove(self, sid: str) -> None:
        """按 id 移除定时任务并持久化。
        Removes the scheduled job by id and persists the change."""
        self._schedules.pop(sid, None)
        self._save()

    def all(self) -> list[Schedule]:
        """返回全部已注册的定时任务列表。
        Returns the list of all registered scheduled jobs."""
        return list(self._schedules.values())

    def set_on_fire(self, cb) -> None:
        """设置到点回调：async (prompt) -> None。Sets the fire callback: async (prompt) -> None."""
        self._on_fire = cb

    def _check_and_fire(self, now: datetime) -> list[str]:
        """检查到点任务并触发（同分钟去重），返回本分钟触发的任务 id 列表。
        Checks which jobs are due and fires them (deduplicated per minute), returning the ids fired this minute."""
        key = now.strftime("%Y-%m-%d %H:%M")
        fired: list[str] = []
        for sid, sc in list(self._schedules.items()):
            if sc.enabled and cron_matches(sc.cron, now) and self._last_fire.get(sid) != key:
                self._last_fire[sid] = key
                fired.append(sid)
        return fired

    async def _loop(self) -> None:
        """后台主循环：每秒检查一次到点任务并触发回调（单次异常被吞掉不影响循环）。
        Background main loop: checks due jobs once per second and fires the callback (a single exception is swallowed and does not stop the loop)."""
        while self._running:
            try:
                fired = self._check_and_fire(datetime.now())
                for sid in fired:
                    sc = self._schedules.get(sid)
                    if sc and self._on_fire:
                        await self._on_fire(sc.prompt)
            except Exception:
                pass
            await asyncio.sleep(1)

    async def start(self) -> None:
        """启动后台调度循环（幂等：已在运行时直接返回）。
        Starts the background scheduling loop (idempotent: returns immediately if already running)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        """停止后台调度循环并取消当前任务。
        Stops the background scheduling loop and cancels the current task."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    def _save(self) -> None:
        """把所有任务序列化为 JSON 写入调度文件。
        Serializes all jobs to JSON and writes them to the schedule file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(sc) for sc in self._schedules.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        """从调度文件加载任务；文件不存在或解析失败时静默忽略。
        Loads jobs from the schedule file; silently ignores a missing file or parse errors."""
        if not self.path.exists():
            return
        try:
            for item in json.loads(self.path.read_text(encoding="utf-8")):
                self._schedules[item["id"]] = Schedule(**item)
        except Exception:
            pass


def get_scheduler() -> Scheduler:
    """返回容器持有的全局 Scheduler（测试可 monkeypatch 本函数）。
    Returns the global Scheduler held by the container (tests may monkeypatch this function)."""
    from core.container import AppContext
    return AppContext.get().scheduler()
