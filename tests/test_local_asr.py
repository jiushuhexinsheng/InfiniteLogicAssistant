# -*- coding: utf-8 -*-
"""本地流式转写单例：缺模型降级、单例复用、wav 解析失败返回空串、与通话开关解耦。
Local streaming ASR singleton: missing-model degradation, singleton reuse, bad-wav empty
string, and decoupling from the call switch."""
import sys
import types

from core.voice import local_asr


def _reset(monkeypatch, model_dir: str = "models/__no_such_dir__"):
    monkeypatch.setattr(local_asr, "_instance", None)
    from core import config
    monkeypatch.setattr(config.settings.voice.asr, "local_model", model_dir)


def test_local_asr_unavailable_without_model(monkeypatch):
    """Review Focus #4：模型缺失 → available()=False，转写返回空串（漏斗降级，不抛）。"""
    _reset(monkeypatch)
    a = local_asr.get_local_asr()
    assert a.available() is False
    assert a.transcribe_wav(b"not a wav") == ""


def test_local_asr_singleton(monkeypatch):
    _reset(monkeypatch)
    assert local_asr.get_local_asr() is local_asr.get_local_asr()


def test_local_asr_bad_wav_returns_empty(monkeypatch):
    _reset(monkeypatch, model_dir="models")  # 目录存在但缺 tokens.txt → 仍 unavailable
    a = local_asr.get_local_asr()
    assert a.transcribe_wav(b"garbage") == ""


def test_local_asr_not_gated_by_call_enabled(monkeypatch, tmp_path):
    """**解耦证据**（2026-10-12）：本地 ASR 升格为 ASR 段设置后不再被 `voice.call.enabled`
    门控 —— 关掉通话模式不应连带禁用本地转写（此前会，是本次修掉的缺陷）。

    Decoupling evidence: local ASR is an ASR-level setting now and is no longer gated by
    `voice.call.enabled`; turning the call mode off must not disable local transcription
    (it used to — the defect this fixes)."""
    from core import config
    d = tmp_path / "asr-model"
    d.mkdir()
    (d / "tokens.txt").write_text("a\n", encoding="utf-8")
    for kind in ("encoder", "decoder", "joiner"):
        (d / f"{kind}-x.onnx").write_text("x", encoding="utf-8")
    monkeypatch.setattr(local_asr, "_instance", None)
    monkeypatch.setattr(config.settings.voice.asr, "local_model", str(d))
    monkeypatch.setattr(config.settings.voice.call, "enabled", False)
    # 假 sherpa_onnx：让 import 成功、构造返回哨兵（不真加载模型）
    fake = types.ModuleType("sherpa_onnx")
    fake.OnlineRecognizer = types.SimpleNamespace(  # type: ignore[attr-defined]
        from_transducer=lambda **kw: object())
    monkeypatch.setitem(sys.modules, "sherpa_onnx", fake)
    assert local_asr.get_local_asr().available() is True


def test_local_asr_status_reports_missing_model(monkeypatch):
    """status() 在缺模型时给出可操作原因（含下载脚本名）。"""
    _reset(monkeypatch)
    ok, reason = local_asr.get_local_asr().status()
    assert ok is False
    assert "fetch_local_asr_model" in reason


def test_local_asr_status_reports_incomplete_files(monkeypatch, tmp_path):
    """tokens.txt 在但三前缀 onnx 缺 → 报「文件不全」（半套状态不能算就绪）。"""
    from core import config
    d = tmp_path / "half"
    d.mkdir()
    (d / "tokens.txt").write_text("a\n", encoding="utf-8")
    monkeypatch.setattr(local_asr, "_instance", None)
    monkeypatch.setattr(config.settings.voice.asr, "local_model", str(d))
    ok, reason = local_asr.get_local_asr().status()
    assert ok is False
    assert "不全" in reason


def test_local_asr_status_available_is_empty_reason(monkeypatch, tmp_path):
    """可用时原因为空串（提示层据此判定「无需提示」）。"""
    from core import config
    d = tmp_path / "ok"
    d.mkdir()
    (d / "tokens.txt").write_text("a\n", encoding="utf-8")
    for kind in ("encoder", "decoder", "joiner"):
        (d / f"{kind}-x.onnx").write_text("x", encoding="utf-8")
    monkeypatch.setattr(local_asr, "_instance", None)
    monkeypatch.setattr(config.settings.voice.asr, "local_model", str(d))
    fake = types.ModuleType("sherpa_onnx")
    fake.OnlineRecognizer = types.SimpleNamespace(  # type: ignore[attr-defined]
        from_transducer=lambda **kw: object())
    monkeypatch.setitem(sys.modules, "sherpa_onnx", fake)
    assert local_asr.get_local_asr().status() == (True, "")
