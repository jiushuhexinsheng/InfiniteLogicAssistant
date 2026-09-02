# -*- coding: utf-8 -*-
"""GUI 自动化 — 启动应用/窗口/点击/输入/截图（pyautogui/pygetwindow，懒加载优雅降级）。GUI automation — launch apps/windows, click, type, screenshot (pyautogui/pygetwindow, lazy-loaded with graceful degradation)."""
import shutil
import subprocess
from typing import Optional


def _launch_command(app_name: str) -> Optional[str]:
    """把应用名解析为可启动命令：which 命中 / 常见别名。Resolve an app name to a launchable command: which hit / common aliases."""
    exe = shutil.which(app_name)
    if exe:
        return exe
    if app_name in ("notepad", "记事本"):
        return "notepad"
    return None


async def gui_activate(app_name: str) -> str:
    """打开已安装应用（免确认）。Launch an installed application (no confirmation)."""
    cmd = _launch_command(app_name)
    if not cmd:
        return f"Error: 未找到应用 {app_name}"
    subprocess.Popen([cmd], shell=True)
    return f"已启动 {app_name}"


async def list_windows() -> str:
    """列出当前可见窗口标题（最多 50 个）。List titles of currently visible windows (up to 50)."""
    try:
        import pygetwindow as gw
    except ImportError:
        return "Error: 需要 pygetwindow（pip install pygetwindow）"
    wins = [w.title for w in gw.getAllWindows() if w.title]
    return "\n".join(wins[:50]) or "无可见窗口"


async def gui_click(x: int, y: int) -> str:
    """在屏幕坐标 (x, y) 处点击。Click at screen coordinates (x, y)."""
    try:
        import pyautogui
    except ImportError:
        return "Error: 需要 pyautogui"
    pyautogui.click(x, y)
    return f"已点击 ({x},{y})"


async def gui_type(text: str) -> str:
    """在当前焦点窗口输入文本。Type text into the currently focused window."""
    try:
        import pyautogui
    except ImportError:
        return "Error: 需要 pyautogui"
    pyautogui.typewrite(text)
    return f"已输入：{text}"


async def gui_screenshot(path: str) -> str:
    """截取全屏并保存到指定路径。Capture the full screen and save it to the given path."""
    try:
        import pyautogui
    except ImportError:
        return "Error: 需要 pyautogui"
    img = pyautogui.screenshot()
    img.save(path)
    return f"截图已保存 {path}"
