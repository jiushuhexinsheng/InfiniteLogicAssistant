# -*- coding: utf-8 -*-
"""环境检测端点响应。Environment detection endpoint responses."""
from typing import Any

from pydantic import BaseModel

from .base import ApiResponse

# ─────────────────────────── detection ───────────────────────────

class DetectionIssue(BaseModel):
    """单条检测问题（级别 + 键 + 描述）。

    A single detection issue (level + key + message).
    """
    level: str
    key: str
    message: str

class ConfigHealthOut(BaseModel):
    """配置健康状态输出。

    Configuration health status output.
    """
    ok: bool
    issues: list[DetectionIssue] = []

class ConnectivityResult(BaseModel):
    """单条连通性检查结果。

    A single connectivity check result.
    """
    name: str
    status: str
    latency_ms: int | None = None
    detail: str = ""

class DetectionReportOut(BaseModel):
    """环境检测报告（系统信息 + 配置健康 + 连通性检查）。

    Environment detection report (system info + config health + connectivity checks).
    """
    environment: dict[str, Any] = {}
    config: ConfigHealthOut
    connectivity: list[ConnectivityResult] = []

class DetectionResponse(ApiResponse):
    """环境检测端点响应。

    ``/api/detection`` response.
    """
    report: DetectionReportOut

