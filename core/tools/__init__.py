# -*- coding: utf-8 -*-
"""工具模块 — 导入触发 @tool 注册到 TOOLS 单例"""
from core.tools import (  # noqa: F401
    basic,
    calculator,
    datetime_tool,
    gui_tools,
    memory_tools,
    schedule_tools,
    search,
    skill_tools,
    weather,
)
from core.tools.base import TOOLS  # noqa: F401
