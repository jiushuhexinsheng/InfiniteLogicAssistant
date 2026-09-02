# -*- coding: utf-8 -*-
"""环境感知（detection 域）— 采集系统信息 → environment.md。Environment sensing (detection domain) — collects system info → environment.md.

采集结果写入独立的 environment.md（人可读、可随时更新）；
Collected results are written to a separate environment.md (human-readable, updatable anytime);
agent 规划时把该文件（或其相关段）注入上下文，让工具参数贴合真实系统。
during planning the agent injects this file (or its relevant sections) into context so tool parameters match the real system.
（原 core/execution/envprobe.py，迁入检测域）
(Originally core/execution/envprobe.py, moved into the detection domain)
"""
import ctypes
import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from core.config import ROOT_DIR

ENVIRONMENT_MD = ROOT_DIR / "environment.md"

_COMMON_TOOLS = [
    "git", "node", "npm", "pnpm", "python", "pip", "docker", "curl", "wget",
    "code", "ffmpeg", "7z", "rg", "conda", "powershell",
]


def _total_memory_gb() -> float:
    """总内存（GB）。Get total physical memory in GB."""
    try:
        import psutil  # 可选：装了更准
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return round(stat.ullTotalPhys / (1024 ** 3), 1)
        except Exception:
            pass
    return 0.0


def _disk_gb() -> dict:
    """磁盘总容量与可用空间（GB）。Get total and free disk space in GB."""
    try:
        total, used, free = shutil.disk_usage("/")
        return {"total_gb": round(total / 2 ** 30, 1), "free_gb": round(free / 2 ** 30, 1)}
    except OSError:
        return {}


def _shell() -> str:
    """当前默认 Shell 路径。Get the current default shell path."""
    if sys.platform == "win32":
        return os.environ.get("COMSPEC", "cmd.exe")
    return os.environ.get("SHELL", "/bin/sh")


def _software() -> dict:
    """探测常用软件及版本（可执行文件 --version）。Probe common tools and their versions (executable --version)."""
    out: Dict[str, str] = {}
    for t in _COMMON_TOOLS:
        p = shutil.which(t)
        if not p:
            continue
        try:
            r = subprocess.run([t, "--version"], capture_output=True, text=True, timeout=5)
            ver = (r.stdout or r.stderr or "").splitlines()
            out[t] = ver[0][:120] if ver else str(p)
        except Exception:
            out[t] = str(p)
    return out


def _net_ok() -> bool:
    """检查外网可达（TCP 8.8.8.8:53）。Check outbound network reachability (TCP 8.8.8.8:53)."""
    try:
        socket.setdefaulttimeout(3)
        socket.create_connection(("8.8.8.8", 53))
        return True
    except Exception:
        return False


async def probe() -> Dict[str, Any]:
    """采集系统信息（纯本地，无外部依赖）。Collect system information (purely local, no external dependencies)."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "hostname": socket.gethostname(),
        "arch": platform.machine(),
        "cpu": platform.processor() or f"{os.cpu_count()} cores",
        "memory_gb": _total_memory_gb(),
        "disk": _disk_gb(),
        "path": os.environ.get("PATH", ""),
        "shell": _shell(),
        "python": sys.version.split()[0],
        "software": _software(),
        "net_ok": _net_ok(),
    }


def _fmt_soft_line(name: str, val: str) -> str:
    """格式化单条软件信息为 Markdown 列表行。Format a single software entry as a Markdown list line."""
    return f"- {name}: `{val}`"


async def write_environment_md(data: Dict[str, Any], path: Path | None = None) -> Path:
    """把采集结果写成结构化 Markdown 并落盘。Write the collected results as structured Markdown to disk."""
    if path is None:
        path = ENVIRONMENT_MD
    disk = data.get("disk") or {}
    lines = [
        "# 环境感知快照",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "> 用途：任务规划时注入上下文；可语音/命令触发「更新环境信息」重新生成",
        "",
        "## 系统",
        "",
        f"- 操作系统：{data.get('os')}",
        f"- 主机名：{data.get('hostname')}",
        f"- 架构：{data.get('arch')}",
        f"- Python：{data.get('python')}",
        "",
        "## 硬件",
        "",
        f"- CPU：{data.get('cpu')}",
        f"- 内存：{data.get('memory_gb')} GB",
    ]
    if disk:
        lines.append(f"- 磁盘：总 {disk.get('total_gb')} GB，可用 {disk.get('free_gb')} GB")
    lines += [
        "",
        "## 环境",
        "",
        f"- Shell：{data.get('shell')}",
        f"- 网络可达：{'是' if data.get('net_ok') else '否'}",
        "",
        f"- PATH：`{data.get('path')}`",
    ]
    soft = data.get("software") or {}
    if soft:
        lines += ["", "## 常用软件", ""]
        lines += [_fmt_soft_line(n, soft[n]) for n in sorted(soft)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def read_environment_md() -> str:
    """读取已生成的环境快照（未生成则先生成）。Read the generated environment snapshot (generate it first if missing)."""
    if not ENVIRONMENT_MD.exists():
        await write_environment_md(await probe())
    return ENVIRONMENT_MD.read_text(encoding="utf-8")
