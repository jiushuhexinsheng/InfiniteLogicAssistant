# -*- coding: utf-8 -*-
"""定时任务执行 — 无人值守：需要澄清/确认的任务自动跳过，只读任务直接执行"""
import asyncio

from core.logger import logger
from core.orchestrator.control import StopController
from core.orchestrator.pipeline import run_pipeline
from core.orchestrator.session import Session


class _SilentChannel:
    """无人值守通道：提问返回空 → 澄清停止、确认拒绝；通知记日志。"""

    async def ask(self, question: str) -> str:
        return ""

    async def notify(self, text: str) -> None:
        logger.info("定时任务通知: {}", text)


async def run_scheduled(prompt: str) -> None:
    """执行一个定时任务 prompt（阻塞到完成；需澄清/确认的自动取消）。"""
    session = Session()
    controller = StopController()
    events: asyncio.Queue = asyncio.Queue()
    try:
        await run_pipeline(prompt, session, events, controller, channel=_SilentChannel())
        logger.info("定时任务完成: {}", prompt)
    except Exception as e:
        logger.warning("定时任务执行失败: {} → {}", prompt, e)
