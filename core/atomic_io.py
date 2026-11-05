# -*- coding: utf-8 -*-
"""原子文本写入：同目录临时文件 + fsync + os.replace。

Atomic text writes: a same-directory temp file + fsync + os.replace.

进程在写入中途崩溃时，目标文件要么是旧内容、要么是完整新内容，不会留下半截
YAML/JSON（半截 config.yaml 会让下一次启动的 pydantic 校验直接失败）。

If the process crashes mid-write, the target is either the old content or the complete
new content — never a half-written YAML/JSON (a truncated config.yaml would make the
next boot fail pydantic validation).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """原子写入 UTF-8 文本。Write UTF-8 text atomically.

    Args:
        path: 目标文件。Target file.
        text: 完整内容。Complete content.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp",
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
