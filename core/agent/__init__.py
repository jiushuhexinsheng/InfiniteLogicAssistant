# -*- coding: utf-8 -*-
"""多智能体 — 子代理基座 / 协调者；并向后兼容旧版 run_agent"""
from core.agent.base import SubAgentResult, run_subagent  # noqa: F401
from core.agent.coordinator import run_coordinator  # noqa: F401
from core.agent.legacy import _trim_history, run_agent  # noqa: F401
