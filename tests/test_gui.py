# -*- coding: utf-8 -*-
"""测试 GUI 启动命令的解析与激活功能。
Tests the GUI launch command parsing and activation functionality.
"""
import pytest

from core.execution.gui import _launch_command, gui_activate


def test_launch_command_known():
    """测试已知应用名能解析出启动命令。Tests that a known app name resolves to a launch command."""
    assert _launch_command("notepad")  # which 命中返回路径


def test_launch_command_chinese_alias():
    """测试中文别名能映射到对应的应用命令。Tests that a Chinese alias maps to the matching app command."""
    assert _launch_command("记事本") == "notepad"


def test_launch_command_unknown():
    """测试未知应用名返回 None。Tests that an unknown app name returns None."""
    assert _launch_command("no_such_app_xyz_123") is None


@pytest.mark.asyncio
async def test_gui_activate_unknown_error():
    """测试激活未知应用时返回错误信息。Tests that activating an unknown app returns an error message."""
    r = await gui_activate("no_such_app_xyz_123")
    assert r.startswith("Error")
