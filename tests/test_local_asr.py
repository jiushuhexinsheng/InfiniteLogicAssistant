# -*- coding: utf-8 -*-
"""本地流式转写单例：缺模型降级、单例复用、wav 解析失败返回空串。Local streaming ASR singleton."""
import wave
import io

from core.voice import local_asr


def _reset(monkeypatch, model_dir: str = "models/__no_such_dir__"):
    monkeypatch.setattr(local_asr, "_instance", None)
    from core import config
    monkeypatch.setattr(config.settings.voice.call, "local_asr_model", model_dir)


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
