# -*- coding: utf-8 -*-
"""Python 代码执行工具（core.execution.python）的测试。
Tests for the Python code execution utility (core.execution.python).
"""
import pytest

from core.execution.python import run_python


@pytest.mark.asyncio
async def test_run_python_prints():
    """测试 run_python 执行代码字符串并捕获标准输出。Tests run_python executing a code string and capturing stdout."""
    r = await run_python("print(1 + 1)")
    assert r.returncode == 0
    assert "2" in r.stdout


@pytest.mark.asyncio
async def test_run_python_file(tmp_path):
    """测试 run_python 直接执行脚本文件。Tests run_python executing a script file directly."""
    p = tmp_path / "a.py"
    p.write_text("print('file-ok')", encoding="utf-8")
    r = await run_python(p)
    assert r.returncode == 0
    assert "file-ok" in r.stdout


@pytest.mark.asyncio
async def test_run_python_utf8_output():
    """测试 run_python 正确处理 UTF-8 编码的中文输出。Tests run_python handling UTF-8 encoded Chinese output correctly."""
    r = await run_python("print('你好世界')")
    assert r.returncode == 0
    assert "你好世界" in r.stdout
