# -*- coding: utf-8 -*-
"""定时任务 — cron（5 段：分 时 日 月 周）注册，到点触发 on_fire(prompt)

持久化到 data/schedules.json；同分钟去重触发。
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
    id: str
    cron: str
    prompt: str
    enabled: bool = True


def _match(field: str, value: int) -> bool:
    if field == "*":
        return True
    try:
        return value == int(field)
    except ValueError:
        return False


def cron_matches(cron: str, now: datetime) -> bool:
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
    def __init__(self, path: Path = SCHEDULES_FILE, on_fire=None):
        self.path = path
        self._schedules: dict[str, Schedule] = {}
        self._last_fire: dict[str, str] = {}
        self._on_fire = on_fire  # async (prompt) -> None
        self._running = False
        self._task: asyncio.Task | None = None
        self._load()

    def add(self, cron: str, prompt: str) -> Schedule:
        sc = Schedule(id=uuid.uuid4().hex[:8], cron=cron, prompt=prompt)
        self._schedules[sc.id] = sc
        self._save()
        return sc

    def remove(self, sid: str) -> None:
        self._schedules.pop(sid, None)
        self._save()

    def list(self) -> list[Schedule]:
        return list(self._schedules.values())

    def set_on_fire(self, cb) -> None:
        """设置到点回调：async (prompt) -> None。"""
        self._on_fire = cb

    def _check_and_fire(self, now: datetime) -> list[str]:
        key = now.strftime("%Y-%m-%d %H:%M")
        fired: list[str] = []
        for sid, sc in list(self._schedules.items()):
            if sc.enabled and cron_matches(sc.cron, now) and self._last_fire.get(sid) != key:
                self._last_fire[sid] = key
                fired.append(sid)
        return fired

    async def _loop(self) -> None:
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
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(sc) for sc in self._schedules.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            for item in json.loads(self.path.read_text(encoding="utf-8")):
                self._schedules[item["id"]] = Schedule(**item)
        except Exception:
            pass


_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
