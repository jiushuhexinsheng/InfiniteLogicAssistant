# -*- coding: utf-8 -*-
"""wttr.in 天气（免 key）

wttr.in weather (no API key required)
"""
import httpx

from core import config
from core.tools.base import tool


@tool("查询城市天气，参数 city 为城市名（中文或拼音）")
async def get_weather(city: str) -> str:
    """查询城市天气（城市名支持中文或拼音）。Query the weather for a city (name in Chinese or pinyin).

    Args:
        city: 城市名。City name.

    Returns:
        天气摘要字符串；失败时返回 "Error: ..."。Weather summary; "Error: ..." on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=config.settings.tools.weather_timeout, follow_redirects=True) as c:
            r = await c.get(f"https://wttr.in/{city}?format=3&lang=zh")
            r.raise_for_status()
            return r.text.strip() or "暂无天气数据"
    except Exception as exc:
        return f"Error: {exc}"
