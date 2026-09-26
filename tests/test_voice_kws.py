# -*- coding: utf-8 -*-
"""本地 KWS 前置闸门（core/voice/kws.py）的测试。

分层语义钉住：KWS 管「是不是我们的词」（发音级、句中提及也命中），
文本层句首规则管「是不是在唤醒」—— 两层各管一半，不互相越权。

Tests for the local KWS pre-gate (core/voice/kws.py). Layered semantics are pinned:
KWS decides "is it our word" (pronunciation level; mid-sentence mentions hit too),
the text-layer leading rule decides "is it a wake" — each layer owns half.
"""
import io
import struct
import wave

import pytest

import core.voice.kws as kws_mod
from core.voice.kws import KwsGate, _wav_to_mono_float, get_kws


def _wav_bytes(samples: list[float], sr: int = 16000, channels: int = 1, width: int = 2) -> bytes:
    """把浮点采样打包成 WAV bytes（供解析测试）。Pack float samples into WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(sr)
        if width == 2:
            w.writeframes(struct.pack(f"<{len(samples)}h", *[int(max(-1, min(1, s)) * 32767) for s in samples]))
        else:
            w.writeframes(struct.pack(f"<{len(samples)}i", *[int(max(-1, min(1, s)) * 2147483647) for s in samples]))
    return buf.getvalue()


# ─── WAV 解析 ───


def test_wav_to_mono_float_16bit():
    """16-bit WAV 解析为 float 并归一化。16-bit WAV parses to normalized floats."""
    data = _wav_bytes([0.0, 0.5, -0.5])
    sr, samples = _wav_to_mono_float(data)
    assert sr == 16000
    assert len(samples) == 3
    assert abs(samples[1] - 0.5) < 0.01


def test_wav_to_mono_float_stereo_takes_first_channel():
    """立体声取首声道（单声道判定不需要混音）。Stereo takes the first channel."""
    data = _wav_bytes([0.5, 0.1, -0.5, 0.1], channels=2)
    _, samples = _wav_to_mono_float(data)
    assert len(samples) == 2
    assert abs(samples[0] - 0.5) < 0.01


def test_wav_to_mono_float_rejects_garbage():
    """非 WAV 字节抛异常（调用方旁路放行交云端）。Garbage bytes raise (caller bypasses to cloud)."""
    with pytest.raises(Exception):
        _wav_to_mono_float(b"not a wav at all")


# ─── 闸门旁路语义（引擎不可用时不阻塞唤醒）───


def test_gate_bypasses_when_model_missing(monkeypatch):
    """模型目录不存在 → 闸门旁路（None），不报错；调用方不得据此触发「音频优先」。
    Missing model dir → the gate bypasses (None), no error; callers must not trigger
    the "audio-first" rule on it."""
    from core import config as config_mod

    monkeypatch.setattr(config_mod, "ROOT_DIR", __import__("pathlib").Path("D:/nonexistent-root"))
    gate = KwsGate()
    assert gate.is_available() is False
    assert gate.detect_wav_bytes(_wav_bytes([0.1] * 1600)) is None  # 旁路 / bypassed


def test_gate_disabled_by_config(monkeypatch):
    """enabled=false → 闸门禁用旁路（None）。enabled=false → gate disabled, bypasses.

    ⚠️ 必须 patch get_settings 而非 settings —— `config.settings` 是 __getattr__ 代理的
    惰性属性，monkeypatch.setattr 直接碰它会在还原时固化成真实模块属性，导致后续测试
    （如 test_api_token_enforced）patch get_settings 全部失效。
    Patch get_settings, NOT settings: `config.settings` is a __getattr__-proxied lazy
    attribute, and monkeypatching it directly freezes it into a real module attribute on
    undo, silently breaking every later test that patches get_settings.
    """
    from core import config as config_mod

    settings = config_mod.settings.model_copy(deep=True)
    settings.voice.kws.enabled = False
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    gate = KwsGate()
    assert gate.is_available() is False
    assert gate.detect_wav_bytes(b"") is None  # 旁路 / bypassed


def test_gate_empty_audio_no_hit():
    """空音频（解析成功但无采样）→ 不命中（合理丢弃，不用上云）。
    Empty audio (parses but no samples) → no hit (dropped; no cloud call needed)."""
    gate = KwsGate()
    # 引擎不可用时是旁路 True；此处只在可用时才有意义 —— 用 monkeypatch 塞一个假 spotter
    # When the engine is unavailable it bypasses with True; inject a fake spotter to pin
    # the empty-audio branch.
    class _FakeSp:
        pass

    gate._loaded = True
    gate._spotter = _FakeSp()
    assert gate.detect_wav_bytes(_wav_bytes([])) is False


# ─── 单例与热重载 ───


def test_get_kws_singleton_and_reload_hook():
    """get_kws 返回单例；_reset_kws 后重建（配置热重载钩子）。
    get_kws returns a singleton; _reset_kws rebuilds it (config reload hook)."""
    a = get_kws()
    b = get_kws()
    assert a is b
    kws_mod._reset_kws()
    c = get_kws()
    assert c is not a
