# -*- coding: utf-8 -*-
"""GUI 自动化工具 — 打开应用 / 列窗口 / 点击 / 输入 / 截图

GUI automation tools — launch apps / list windows / click / type / screenshot
"""
from core.execution.gui import (
    gui_activate, gui_click, gui_screenshot, gui_type, list_windows,
)
from core.tools.base import tool


@tool("打开已安装的应用（如 notepad）")
async def gui_activate_tool(app_name: str) -> str:
    """打开已安装的应用。Launch an installed application.

    Args:
        app_name: 应用名称（如 notepad）。Application name (e.g. notepad).

    Returns:
        执行结果。Execution result.
    """
    return await gui_activate(app_name)


@tool("列出当前可见窗口标题", risk="read")
async def list_windows_tool() -> str:
    """列出当前可见窗口标题。List titles of currently visible windows.

    Returns:
        窗口标题列表。List of window titles.
    """
    return await list_windows()


@tool("模拟鼠标点击屏幕坐标", risk="exec")
async def gui_click_tool(x: int, y: int) -> str:
    """模拟鼠标点击屏幕坐标。Simulate a mouse click at screen coordinates.

    Args:
        x: 屏幕 x 坐标。Screen x coordinate.
        y: 屏幕 y 坐标。Screen y coordinate.

    Returns:
        执行结果。Execution result.
    """
    return await gui_click(x, y)


@tool("模拟键盘输入文本", risk="exec")
async def gui_type_tool(text: str) -> str:
    """模拟键盘输入文本。Simulate typing text via keyboard.

    Args:
        text: 要输入的文本。Text to type.

    Returns:
        执行结果。Execution result.
    """
    return await gui_type(text)


@tool("截取当前屏幕保存到路径", risk="read")  # 只读：读屏不改系统状态，归 read 免询问
async def gui_screenshot_tool(path: str) -> str:
    """截取当前屏幕并保存到指定路径。Capture the current screen and save it to the given path.

    Args:
        path: 保存路径。Save path.

    Returns:
        执行结果。Execution result.
    """
    return await gui_screenshot(path)
