# -*- coding: utf-8 -*-
"""基础工具集 — 够底层、可组合（grep/find/读写/解析/shell/python/系统感知/目录）

Basic tool set — low-level and composable (grep/find/read-write/parse/shell/python/system-probe/directory)
"""
import json
import re
from pathlib import Path
from typing import Any

from core.detection.environment import read_environment_md
from core.execution.fs import list_dir as _fs_list_dir
from core.execution.fs import read_doc, stat_path as _fs_stat
from core.execution.python import run_python
from core.execution.shell import run_shell
from core.tools.base import tool

MAX_GREP_HITS = 50
MAX_FIND_HITS = 100


@tool("按内容搜索文件（grep 语义），返回 文件:行号: 匹配行")
async def grep_file(pattern: str, path: str = ".", ext: str = "") -> str:
    """按内容搜索文件（grep 语义），返回 "文件:行号: 匹配行"。

    Search files by content (grep semantics), returning "file:line: matched line".

    Args:
        pattern: 正则表达式。Regular expression.
        path: 搜索根目录，默认当前目录。Root directory to search; defaults to ".".
        ext: 仅匹配该扩展名（可选）。Only match files with this extension (optional).

    Returns:
        匹配结果字符串；无匹配时返回 "无匹配"。Matched lines; "无匹配" when nothing matches.
    """
    root = Path(path)
    ext = ext.lstrip(".")
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"Error: 正则无效: {exc}"
    hits: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if ext and p.suffix.lower().lstrip(".") != ext:
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{p}:{i}: {line.strip()[:200]}")
                    if len(hits) >= MAX_GREP_HITS:
                        break
        except Exception:
            continue
        if len(hits) >= MAX_GREP_HITS:
            break
    return "\n".join(hits) or "无匹配"


@tool("按文件名搜索文件，返回路径列表")
async def find_files(name_pattern: str, dir: str = ".") -> str:
    """按文件名模糊搜索文件，返回路径列表。

    Find files by fuzzy name matching, returning a list of paths.

    Args:
        name_pattern: 文件名包含的字符串。Substring the filename must contain.
        dir: 搜索目录，默认当前目录。Directory to search; defaults to ".".

    Returns:
        路径列表字符串；未找到时返回 "未找到"。List of paths; "未找到" when none found.
    """
    root = Path(dir)
    out: list[str] = []
    for p in root.rglob("*"):
        if p.is_file() and name_pattern in p.name:
            out.append(str(p))
            if len(out) >= MAX_FIND_HITS:
                break
    return "\n".join(out) or "未找到"


@tool("读取文件内容（文本）")
async def read_file(path: str) -> str:
    """读取文本文件内容。Read the content of a text file.

    Args:
        path: 文件路径。File path.

    Returns:
        文件内容字符串。File content string.
    """
    return Path(path).read_text(encoding="utf-8", errors="replace")


@tool("写入文件内容（覆盖；父目录自动创建）", risk="write")
async def write_file(path: str, content: str) -> str:
    """覆盖写入文件（父目录自动创建）。Overwrite a file (parent directories are created automatically).

    Args:
        path: 文件路径。File path.
        content: 要写入的内容。Content to write.

    Returns:
        成功提示。Success message.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已写入 {path}"


@tool("按格式解析文档（json/yaml/toml/csv/xlsx/sqlite/ini 等）")
async def parse_doc(path: str) -> str:
    """按格式解析文档（json/yaml/toml/csv/xlsx/sqlite/ini 等），返回 JSON 字符串。

    Parse a document by format (json/yaml/toml/csv/xlsx/sqlite/ini, etc.), returning a JSON string.

    Args:
        path: 文档路径。Document path.

    Returns:
        解析结果的 JSON 字符串。Parsed result as JSON string.
    """
    data = await read_doc(path)
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@tool("列出目录内容")
async def list_dir(path: str = ".") -> str:
    """列出目录内容，目录项加 [目录] 标记。List directory entries, marking directories with [目录].

    Args:
        path: 目录路径，默认当前目录。Directory path; defaults to ".".

    Returns:
        条目列表字符串。List of entries as string.
    """
    entries = await _fs_list_dir(path)
    return "\n".join(f"{'[目录]' if e['is_dir'] else '      '} {e['name']}" for e in entries)


@tool("获取文件/目录元数据")
async def stat_path(path: str) -> str:
    """获取文件/目录元数据（大小、时间等）。Get file/directory metadata (size, timestamps, etc.).

    Args:
        path: 路径。Path.

    Returns:
        元数据的 JSON 字符串。Metadata as JSON string.
    """
    st = await _fs_stat(path)
    return json.dumps(st, ensure_ascii=False, indent=2)


@tool("执行 Shell 命令（返回 stdout/stderr/退出码）", risk="exec")
async def run_shell_tool(command: str, cancel: Any | None = None) -> str:
    """执行 Shell 命令，返回 stdout/stderr/退出码。Run a shell command, returning stdout/stderr/exit code.

    Args:
        command: 要执行的命令。Command to run.
        cancel: 取消令牌（由 acall 注入）。Cancel token (injected by acall).

    Returns:
        "exit=退出码\nstdoutstderr" 格式的结果字符串。Formatted result string.
    """
    r = await run_shell(command, timeout=30, cancel=cancel)
    return f"exit={r.returncode}\n{r.stdout}{r.stderr}".strip()


@tool("执行 Python 代码（独立子进程，返回 stdout/stderr/退出码）", risk="exec")
async def run_python_tool(code: str, cancel: Any | None = None) -> str:
    """在独立子进程中执行 Python 代码，返回 stdout/stderr/退出码。

    Run Python code in a separate subprocess, returning stdout/stderr/exit code.

    Args:
        code: 要执行的代码。Code to run.
        cancel: 取消令牌（由 acall 注入）。Cancel token (injected by acall).

    Returns:
        "exit=退出码\nstdoutstderr" 格式的结果字符串。Formatted result string.
    """
    r = await run_python(code, timeout=30, cancel=cancel)
    return f"exit={r.returncode}\n{r.stdout}{r.stderr}".strip()


@tool("获取环境感知快照（读取 environment.md；未生成则自动采集）")
async def system_probe() -> str:
    """获取环境感知快照（读取 environment.md；未生成则自动采集）。

    Get an environment-awareness snapshot (reads environment.md, auto-collects if missing).

    Returns:
        环境快照文本。Environment snapshot text.
    """
    return await read_environment_md()
