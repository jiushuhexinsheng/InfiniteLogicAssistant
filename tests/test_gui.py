# -*- coding: utf-8 -*-
import pytest

from core.execution.gui import _launch_command, gui_activate


def test_launch_command_known():
    assert _launch_command("notepad") == "notepad"


def test_launch_command_unknown():
    assert _launch_command("no_such_app_xyz_123") is None


@pytest.mark.asyncio
async def test_gui_activate_unknown_error():
    r = await gui_activate("no_such_app_xyz_123")
    assert r.startswith("Error")
