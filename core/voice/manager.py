# -*- coding: utf-8 -*-
"""桌面语音监听管理器 — 全局单例，供 /api/voice/toggle 开关后端麦克风"""
import asyncio

from core.config import cfg
from core.logger import logger
from core.orchestrator.control import StopController
from core.orchestrator.pipeline import run_pipeline
from core.orchestrator.session import Session
from core.voice.wake import WakeListener

_listener: WakeListener | None = None
_running = False


class _SilentChannel:
    """无人值守通道：提问返回空 → 澄清/确认自动跳过。"""

    async def ask(self, question: str) -> str:
        return ""

    async def notify(self, text: str) -> None:
        logger.info("语音任务通知: {}", text)


def is_running() -> bool:
    return _running


def _process_utterance(text: str) -> None:
    """把识别到的语音文本喂入编排（后台任务）。"""

    async def _run():
        session = Session()
        controller = StopController()
        events: asyncio.Queue = asyncio.Queue()
        try:
            await run_pipeline(text, session, events, controller, channel=_SilentChannel())
        except Exception as e:
            logger.warning("语音处理失败: {}", e)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run())
    else:
        asyncio.ensure_future(_run())


def start() -> bool:
    global _listener, _running
    if _running:
        return True
    model = cfg("voice.wake_word.local_model", "") or cfg("voice.wake_word.model_path", "")
    listener = WakeListener(model_path=model)
    if not listener.start(on_utterance=_process_utterance):
        logger.warning("语音监听启动失败（检查模型/麦克风）")
        return False
    _listener = listener
    _running = True
    logger.info("桌面语音监听已启动")
    return True


def stop() -> None:
    global _listener, _running
    if _listener:
        try:
            _listener.stop()
        except Exception:
            pass
    _listener = None
    _running = False
    logger.info("桌面语音监听已停止")


def toggle() -> bool:
    """返回切换后的运行状态。"""
    return start() if not _running else (stop(), False)[1]
