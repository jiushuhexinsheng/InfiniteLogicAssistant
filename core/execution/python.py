# -*- coding: utf-8 -*-
"""Python 脚本执行 — 独立子进程，避免污染宿主解释器

代码字符串写临时 .py 再执行，避免引号/换行转义问题；`-X utf8` 保证输出 UTF-8。
"""
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from core.execution.shell import ShellResult, run_shell


async def run_python(
    code: str | Path,
    *,
    cwd: str | None = None,
    timeout: float = 60,
    cancel: Any | None = None,
) -> ShellResult:
    """执行 Python 代码字符串或 .py 文件（独立子进程）。"""
    if isinstance(code, Path):
        cmd = f'"{sys.executable}" -X utf8 "{code}"'
        return await run_shell(cmd, cwd=cwd, timeout=timeout, cancel=cancel)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    cmd = f'"{sys.executable}" -X utf8 "{tmp}"'
    try:
        return await run_shell(cmd, cwd=cwd, timeout=timeout, cancel=cancel)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
