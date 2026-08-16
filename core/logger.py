# -*- coding: utf-8 -*-
"""日志模块 — 基于 loguru，对齐 消息提醒播报"""
import sys
from pathlib import Path

from loguru import logger

LOG_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_FILE = LOG_DIR / "agent.log"
AUDIT_FILE = LOG_DIR / "audit.log"


def _not_audit(record) -> bool:
    return not record["extra"].get("audit", False)


def _is_audit(record) -> bool:
    return record["extra"].get("audit", False)


logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>",
    level="INFO",
    colorize=True,
    filter=_not_audit,
)
logger.add(
    LOG_FILE,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{function}:{line} | {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8",
    filter=_not_audit,
)
# 审计日志：独立文件（工具执行 / 高风险确认），不混入 agent.log
logger.add(
    AUDIT_FILE,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
    level="INFO",
    rotation="10 MB",
    retention="90 days",
    encoding="utf-8",
    filter=_is_audit,
)

_audit_logger = logger.bind(audit=True)


def audit(message: str) -> None:
    """写一条审计记录（data/audit.log）。"""
    _audit_logger.info(message)


__all__ = ["logger", "audit"]
