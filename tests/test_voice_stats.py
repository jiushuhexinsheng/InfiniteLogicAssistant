# -*- coding: utf-8 -*-
"""语音上传成本统计端点（P2-6）：audit.log 的 audio-upload via=stream 计数与按天趋势。

Voice upload cost stats endpoint (P2-6): audio-upload via=stream counts and per-day
trend from the audit log.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

import server as server_module
from core.api.voice import stats as stats_mod

# 最后一条必须落在「今天」——近 7 日窗口的最后一天断言依赖它。
# 写死日期只在提交当天通过（date-bomb），故动态生成。
_TODAY = date.today().isoformat()

_AUDIT样本 = f"""\
2026-10-01 10:00:00.000 | audio-upload via=stream chars=9 text='衍衡，打开记事本'
2026-10-01 11:00:00.000 | audio-upload via=stream chars=5 text='今天几号'
2026-10-02 09:00:00.000 | audio-upload via=stream chars=8 text='明天几点下雨'
2026-10-02 09:30:00.000 | call-funnel text verdict=command hit=1 stage=l2 relax=0 text='明天几点下雨'
2026-10-02 10:00:00.000 | kws-stream hit=1 keyword='衍衡'
{_TODAY} 08:00:00.000 | audio-upload via=stream chars=3 text='查一下新闻'
"""


def _write_audit(tmp_path, content: str):
    p = tmp_path / "audit.log"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def client(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    monkeypatch.setattr(server_module, "WEB_DIST_DIR", dist)
    return TestClient(server_module.app)


def test_parse_counts_stream_only():
    """只数 audio-upload via=stream；funnel/kws 等非上传行不计。
    Only audio-upload via=stream counts; funnel/kws lines don't."""
    counts = stats_mod.parse_upload_lines(_AUDIT样本.splitlines())
    assert counts == {"stream": 4}


def test_parse_per_day_trend():
    """按天分组（各 via 分列），无上传的日期不出现（前端补零）。
    Grouped by day (per-via columns); days with no uploads are absent (frontend pads)."""
    days = stats_mod.parse_days(_AUDIT样本.splitlines())
    assert days == {
        "2026-10-01": {"stream": 2},
        "2026-10-02": {"stream": 1},
        _TODAY: {"stream": 1},
    }


def test_endpoint_returns_counts_and_trend(client, monkeypatch, tmp_path):
    """端点：total + stream 计数 + 按天趋势 + 窗口内补零的近 7 日序列。
    Endpoint: total + stream counts + daily trend + a padded 7-day window."""
    _write_audit(tmp_path, _AUDIT样本)
    import core.logger as logger_mod
    monkeypatch.setattr(logger_mod, "AUDIT_FILE", tmp_path / "audit.log")
    r = client.get("/api/voice/upload-stats")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["total"] == 4
    assert d["by_via"] == {"stream": 4}
    assert d["days"] and len(d["days"]) == 7      # 近 7 日（含今天）补零
    last = d["days"][-1]
    assert last["stream"] == 1
    assert set(last) >= {"date", "stream"}


def test_endpoint_never_leaks_transcript(client, monkeypatch, tmp_path):
    """安全口径：audit 行含转写原文，响应只回计数与日期，绝不回 text/command。
    Security: audit lines carry raw transcripts; the response returns counts and dates
    only — never text/command."""
    _write_audit(tmp_path, "2026-10-07 08:00:00.000 | audio-upload via=stream chars=9 "
                           "text='绝密内部项目代号'\n")
    import core.logger as logger_mod
    monkeypatch.setattr(logger_mod, "AUDIT_FILE", tmp_path / "audit.log")
    body = client.get("/api/voice/upload-stats").text
    assert "绝密" not in body and "text=" not in body


def test_endpoint_missing_file_returns_zeros(client, monkeypatch, tmp_path):
    """文件不存在（全新安装）→ 全零不炸。Missing file (fresh install) → zeros, no crash."""
    import core.logger as logger_mod
    monkeypatch.setattr(logger_mod, "AUDIT_FILE", tmp_path / "nope.log")
    d = client.get("/api/voice/upload-stats").json()
    assert d["ok"] is True and d["total"] == 0 and d["by_via"]["stream"] == 0
    assert len(d["days"]) == 7 and all(x["stream"] == 0 for x in d["days"])
