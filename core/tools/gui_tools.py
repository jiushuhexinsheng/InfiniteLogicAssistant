# -*- coding: utf-8 -*-
"""GUI 自动化工具 — 打开应用 / 列窗口 / 点击 / 输入 / 截图"""
from core.execution.gui import (
    gui_activate, gui_click, gui_screenshot, gui_type, list_windows,
)
from core.tools.base import tool


@tool("打开已安装的应用（如 notepad）")
async def gui_activate_tool(app_name: str) -> str:
    return await gui_activate(app_name)


@tool("列出当前可见窗口标题", risk="read")
async def list_windows_tool() -> str:
    return await list_windows()


@tool("模拟鼠标点击屏幕坐标", risk="exec")
async def gui_click_tool(x: int, y: int) -> str:
    return await gui_click(x, y)


@tool("模拟键盘输入文本", risk="exec")
async def gui_type_tool(text: str) -> str:
    return await gui_type(text)


@tool("截取当前屏幕保存到路径", risk="exec")
async def gui_screenshot_tool(path: str) -> str:
    return await gui_screenshot(path)
