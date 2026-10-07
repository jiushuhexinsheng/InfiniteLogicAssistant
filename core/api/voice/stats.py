# -*- coding: utf-8 -*-
"""语音上传成本统计 — audit.log 的 audio-upload via= 三前缀计数与按天趋势（P2-6）。

Voice upload cost stats — audio-upload via= counts and per-day trend from the audit
log (P2-6).

⚠️ **安全口径**：audit 行携带转写原文（text=…），本端点**只回计数与日期**，绝不回放
任何行文本——成本仪表不需要知道说了什么。
⚠️ Security: audit lines carry raw transcripts (text=…). This endpoint returns counts
and dates only, never any line text — a cost dashboard does not need to know what
was said.
"""
import re
from datetime import date, timedelta

from fastapi import APIRouter
from core.api.schemas import UploadStatsResponse

router = APIRouter()

# 三个上传来源前缀（与 wiki/Security.md 成本口径一致；kws-gate/call-funnel 不算上传）。
# The three upload sources (aligned with wiki/Security.md cost accounting; kws-gate /
# call-funnel lines are not uploads).
_VIAS = ("wake", "transcribe", "call-segment")

# loguru 行首 `YYYY-MM-DD HH:MM:SS.mmm | …`；取日期与 via（只认三前缀，其余行忽略）。
# loguru line head `YYYY-MM-DD HH:MM:SS.mmm | …`; take the date and via (whitelist only).
_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s.*\|\saudio-upload via=(" + "|".join(re.escape(v) for v in _VIAS) + r")\b"
)

# 趋势窗口：近 7 日（含今天）。Trend window: the last 7 days (inclusive).
_TREND_DAYS = 7


def parse_upload_lines(lines) -> dict[str, int]:
    """统计三前缀计数（仅 audio-upload via= 白名单行）。

    Count the three via prefixes (whitelisted ``audio-upload via=`` lines only).
    """
    counts = {v: 0 for v in _VIAS}
    for line in lines:
        m = _LINE_RE.match(line)
        if m:
            counts[m.group(2)] += 1
    return counts


def parse_days(lines) -> dict[str, dict[str, int]]:
    """按日期分组的三前缀计数（无上传日不出现，由调用方补零）。

    Per-date via counts (days without uploads are absent; the caller pads).
    """
    days: dict[str, dict[str, int]] = {}
    for line in lines:
        m = _LINE_RE.match(line)
        if not m:
            continue
        d, via = m.group(1), m.group(2)
        row = days.setdefault(d, {v: 0 for v in _VIAS})
        row[via] += 1
    return days


def _read_lines() -> list[str]:
    """动态读 core.logger.AUDIT_FILE（测试 monkeypatch 该属性即隔离真实日志）。

    Reads ``core.logger.AUDIT_FILE`` dynamically (tests patch that attribute to stay
    hermetic); a missing file is an empty log.
    """
    from core import logger as logger_mod
    try:
        return logger_mod.AUDIT_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


@router.get("/voice/upload-stats", response_model=UploadStatsResponse)
async def voice_upload_stats():
    """三前缀计数 + 近 7 日趋势（成本仪表数据源；只回计数与日期）。

    Per-via counts + 7-day trend (the cost-dashboard feed; counts and dates only).
    """
    lines = _read_lines()
    by_via = parse_upload_lines(lines)
    by_day = parse_days(lines)
    today = date.today()
    days = []
    for i in range(_TREND_DAYS - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        row = by_day.get(d, {v: 0 for v in _VIAS})
        days.append({"date": d, **row})
    return UploadStatsResponse(ok=True, total=sum(by_via.values()),
                               by_via=by_via, days=days)
