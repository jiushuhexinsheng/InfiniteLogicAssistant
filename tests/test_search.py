# -*- coding: utf-8 -*-
"""core/tools/search.py — 搜索失败应给出可操作的中文提示（而非裸异常文本）"""
from core.tools.search import _describe_error


def test_describe_error_actionable():
    msg = _describe_error(ConnectionError("refused"))
    assert "联网搜索失败" in msg
    assert "检查网络" in msg
    assert "refused" in msg  # 保留原始异常详情


def test_describe_error_rate_limit_hint():
    msg = _describe_error(Exception("ratelimit"))
    assert "限流" in msg
