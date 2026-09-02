# -*- coding: utf-8 -*-
"""当前日期时间工具

Current date and time tool
"""
from datetime import datetime

from core.tools.base import tool


@tool("获取当前日期与时间，返回中文格式")
def get_datetime() -> str:
    """获取当前日期与时间，返回中文格式（如 "2024年01月01日 12:00:00"）。

    Get the current date and time in Chinese format (e.g. "2024年01月01日 12:00:00").

    Returns:
        格式化后的日期时间字符串。Formatted date-time string.
    """
    return datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
