# -*- coding: utf-8 -*-
import pytest

from core.execution.python import run_python


@pytest.mark.asyncio
async def test_run_python_prints():
    r = await run_python("print(1 + 1)")
    assert r.returncode == 0
    assert "2" in r.stdout


@pytest.mark.asyncio
async def test_run_python_file(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("print('file-ok')", encoding="utf-8")
    r = await run_python(p)
    assert r.returncode == 0
    assert "file-ok" in r.stdout


@pytest.mark.asyncio
async def test_run_python_utf8_output():
    r = await run_python("print('你好世界')")
    assert r.returncode == 0
    assert "你好世界" in r.stdout
