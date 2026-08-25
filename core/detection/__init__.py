# -*- coding: utf-8 -*-
"""检测域 — 环境感知 + 配置校验 + 连通性 三合一

供启动自检、`python main.py test`、`GET /api/detection`（设置页「检测」按钮）使用。
"""
import asyncio

from core import config
from core.detection import connectivity, environment, validator
from core.detection.connectivity import CheckResult, check_asr, check_llm, check_tts, run_checks
from core.detection.environment import (
    ENVIRONMENT_MD, probe, read_environment_md, write_environment_md,
)
from core.detection.validator import ConfigHealth, Issue, validate

__all__ = [
    "connectivity", "environment", "validator",
    "CheckResult", "check_asr", "check_llm", "check_tts", "run_checks",
    "ENVIRONMENT_MD", "probe", "read_environment_md", "write_environment_md",
    "ConfigHealth", "Issue", "validate",
    "run_all",
]


async def run_all() -> dict:
    """聚合检测：环境快照 + 配置健康 + 三项连通性。"""
    env, conns = await asyncio.gather(environment.probe(), connectivity.run_checks())
    health = validate(config.get_settings())
    return {
        "environment": env,
        "config": health.as_dict(),
        "connectivity": [c.as_dict() for c in conns],
    }
