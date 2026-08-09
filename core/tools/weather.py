# -*- coding: utf-8 -*-
"""wttr.in 天气（免 key）"""
import httpx

from core.config import cfg
from core.tools.base import tool


@tool("查询城市天气，参数 city 为城市名（中文或拼音）")
async def get_weather(city: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=cfg("tools.weather_timeout", 10), follow_redirects=True) as c:
            r = await c.get(f"https://wttr.in/{city}?format=3&lang=zh")
            r.raise_for_status()
            return r.text.strip() or "暂无天气数据"
    except Exception as exc:
        return f"Error: {exc}"
