# -*- coding: utf-8 -*-
"""当前日期时间工具"""
from datetime import datetime

from core.tools.base import tool


@tool("获取当前日期与时间，返回中文格式")
def get_datetime() -> str:
    return datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
