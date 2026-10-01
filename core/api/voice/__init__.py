# -*- coding: utf-8 -*-
"""voice 域 API — 配置 / TTS / ASR 转写 / 编排 SSE 入口（唯一 agent 路径）

voice domain API — config / TTS / ASR transcription / orchestration SSE entry
(the only agent path)

按端点域拆到同目录子模块(meta / tts / wake / run),各自持有 APIRouter;
本包聚合出 `router` 供 server.py 挂载(`voice.router` 零改动),并 re-export
test_sse_resume 直驱的运行流辅助(`_stream_run` 等)。
"""
from fastapi import APIRouter

from .meta import router as _meta_router
from .run import router as _run_router
from .tts import router as _tts_router
from .wake import router as _wake_router

router = APIRouter()
router.include_router(_meta_router)
router.include_router(_tts_router)
router.include_router(_wake_router)
router.include_router(_run_router)

# 测试直驱的 SSE 辅助保持包级可达（tests/test_sse_resume.py）。
# Run-stream helpers stay reachable at package level (tests/test_sse_resume.py).
from .run import (  # noqa: E402  (聚合完 router 再导出)
    _arm_grace,
    _replay_then_live,
    _retire_run,
    _stream_run,
)

__all__ = [
    "router",
    "_arm_grace",
    "_replay_then_live",
    "_retire_run",
    "_stream_run",
]
