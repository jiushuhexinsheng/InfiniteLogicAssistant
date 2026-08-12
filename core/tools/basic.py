# -*- coding: utf-8 -*-
"""基础工具集 — 够底层、可组合（grep/find/读写/解析/shell/python/系统感知/目录）"""
import json
import re
from pathlib import Path

from core.execution.envprobe import read_environment_md
from core.execution.fs import list_dir as _fs_list_dir
from core.execution.fs import read_doc, stat_path as _fs_stat
from core.execution.python import run_python
from core.execution.shell import run_shell
from core.tools.base import tool

MAX_GREP_HITS = 50
MAX_FIND_HITS = 100


@tool("按内容搜索文件（grep 语义），返回 文件:行号: 匹配行")
async def grep_file(pattern: str, path: str = ".", ext: str = "") -> str:
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
    return Path(path).read_text(encoding="utf-8", errors="replace")


@tool("写入文件内容（覆盖；父目录自动创建）", risk="write")
async def write_file(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已写入 {path}"


@tool("按格式解析文档（json/yaml/toml/csv/xlsx/sqlite/ini 等）")
async def parse_doc(path: str) -> str:
    data = await read_doc(path)
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@tool("列出目录内容")
async def list_dir(path: str = ".") -> str:
    entries = await _fs_list_dir(path)
    return "\n".join(f"{'[目录]' if e['is_dir'] else '      '} {e['name']}" for e in entries)


@tool("获取文件/目录元数据")
async def stat_path(path: str) -> str:
    st = await _fs_stat(path)
    return json.dumps(st, ensure_ascii=False, indent=2)


@tool("执行 Shell 命令（返回 stdout/stderr/退出码）", risk="exec")
async def run_shell_tool(command: str) -> str:
    r = await run_shell(command, timeout=30)
    return f"exit={r.returncode}\n{r.stdout}{r.stderr}".strip()


@tool("执行 Python 代码（独立子进程，返回 stdout/stderr/退出码）", risk="exec")
async def run_python_tool(code: str) -> str:
    r = await run_python(code, timeout=30)
    return f"exit={r.returncode}\n{r.stdout}{r.stderr}".strip()


@tool("获取环境感知快照（读取 environment.md；未生成则自动采集）")
async def system_probe() -> str:
    return await read_environment_md()
