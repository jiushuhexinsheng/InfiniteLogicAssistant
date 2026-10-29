# -*- coding: utf-8 -*-
"""本地引擎加载失败的缓存语义：失败不得永久缓存（模型补装/瞬时错误后可自愈）。

Local engine load-failure caching semantics: failures must not be cached forever, so
a later session retries after the model is installed or a transient error clears.
"""

import sys
import threading
import types

import pytest

from core.voice.local.sherpa_onnx.asr import (
    AsrOptions,
    AsrSession,
    StreamingAsrEngine,
    _decode_must_serialize,
)
from core.voice.local.sherpa_onnx.kws import KwsEngine, KwsOptions
from core.voice.local.sherpa_onnx.tts import TtsEngine, TtsOptions
from core.voice.local.sherpa_onnx.vad import VadEngine, VadOptions


def test_runtime_maps_min_speech_ms_to_vad_option(monkeypatch):
    """vad.min_speech_ms（毫秒）→ VadOptions.min_speech_s（秒）。

    The config knob is in ms; the sherpa VAD option is in seconds.
    """
    from core import config
    from core.voice.local.runtime import LocalRuntime

    monkeypatch.setattr(config.settings.voice.vad, "min_speech_ms", 100)
    runtime = LocalRuntime()
    assert runtime.vad().opts.min_speech_s == pytest.approx(0.1)


def test_asr_load_failure_is_retried(tmp_path):
    """首次加载失败（模型目录缺失）不置 _loaded；补齐 tokens 后再问会重新尝试。
    A first failed load (missing model dir) must not set _loaded; after tokens appear
    the next status() retries instead of replaying the cached failure."""
    eng = StreamingAsrEngine(AsrOptions(model_dir=str(tmp_path / "missing")))
    ok, reason = eng.status()
    assert ok is False
    assert "tokens.txt" in reason
    assert eng._loaded is False

    d = tmp_path / "missing"
    d.mkdir()
    (d / "tokens.txt").write_text("x", encoding="utf-8")
    ok2, reason2 = eng.status()
    assert ok2 is False
    assert "tokens.txt" not in reason2          # 越过存在性检查，说明确已重试。Retried.
    assert eng._loaded is False


def test_vad_load_failure_is_retried(tmp_path):
    """VAD 同理：模型文件缺失的失败不缓存，补上文件后会重新尝试加载。
    Same for VAD: a missing model file is not cached, so adding it triggers a retry."""
    eng = VadEngine(VadOptions(model=str(tmp_path / "missing.onnx")))
    ok, reason = eng.status()
    assert ok is False
    assert "不存在" in reason
    assert eng._loaded is False

    (tmp_path / "missing.onnx").write_bytes(b"not a real model")
    ok2, reason2 = eng.status()
    assert "不存在" not in reason2              # 已重试到加载阶段。Retried past existence.
    assert eng._loaded is True                  # 第二次尝试才写缓存。Cached only on success.


def test_kws_load_failure_is_retried(tmp_path):
    """KWS 失败同样不缓存（模型补装后可自愈）。KWS failures are not cached either."""
    eng = KwsEngine(KwsOptions(model_dir=str(tmp_path / "missing"), keywords=("衍衡",)))
    ok, _ = eng.status()
    assert ok is False
    assert eng._loaded is False


def test_tts_load_failure_is_retried(tmp_path):
    """TTS 失败同样不缓存（模型补装后可自愈）。TTS failures are not cached either."""
    eng = TtsEngine(TtsOptions(model_dir=str(tmp_path / "missing")))
    ok, _ = eng.status()
    assert ok is False
    assert eng._loaded is False


# ─── 并发：冷加载只构造一次；CPU 解码不持锁 ───


def _touch_asr_model(tmp_path):
    """造一个通过存在性检查的 ASR 模型目录。Create a model dir that passes existence checks."""
    d = tmp_path / "asr"
    d.mkdir()
    (d / "tokens.txt").write_text("x", encoding="utf-8")
    for kind in ("encoder", "decoder", "joiner"):
        (d / f"{kind}.onnx").write_bytes(b"x")
    return d


def test_asr_load_once_under_concurrency(tmp_path, monkeypatch):
    """并发冷启动只构造一个 recognizer（_load 的双重检查锁）。

    Concurrent cold starts construct exactly one recognizer (the double-checked load lock)."""
    d = _touch_asr_model(tmp_path)
    calls: list[int] = []

    class FakeRecognizer:
        @classmethod
        def from_transducer(cls, **_kw):
            calls.append(1)
            return object()

    fake = types.SimpleNamespace(OnlineRecognizer=FakeRecognizer)
    monkeypatch.setitem(sys.modules, "sherpa_onnx", fake)

    eng = StreamingAsrEngine(AsrOptions(model_dir=str(d)))
    barrier = threading.Barrier(8)
    results: list[tuple[bool, str]] = []

    def worker():
        barrier.wait()
        results.append(eng.status())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results and all(ok for ok, _ in results)
    assert len(calls) == 1


class _NoReadyRecognizer:
    """永远没有可解码块的 recognizer。A recognizer with nothing ready to decode."""

    def is_ready(self, _stream):
        return False

    def get_result(self, _stream):
        return ""


class _RecordingLock:
    def __init__(self) -> None:
        self.used = False

    def __enter__(self):
        self.used = True
        return self

    def __exit__(self, *_exc):
        return False


def test_asr_cpu_decode_does_not_take_lock():
    """CPU provider：解码不进入引擎锁（不同 stream 可并发）。

    CPU: decode must not enter the engine lock (distinct streams decode concurrently)."""
    eng = StreamingAsrEngine(AsrOptions(model_dir="/nonexistent"))
    eng._recognizer = _NoReadyRecognizer()
    eng._loaded = True
    eng._serialize_decode = False
    lock = _RecordingLock()
    eng._lock = lock

    assert AsrSession(eng, stream=object()).decode() == ""
    assert lock.used is False


def test_asr_non_cpu_decode_takes_lock():
    """非 CPU provider：解码仍串行化（CUDA/TensorRT 不保证线程安全）。

    Non-CPU: decoding stays serialised (CUDA/TensorRT are not guaranteed thread-safe)."""
    eng = StreamingAsrEngine(AsrOptions(model_dir="/nonexistent"))
    eng._recognizer = _NoReadyRecognizer()
    eng._loaded = True
    eng._serialize_decode = True
    lock = _RecordingLock()
    eng._lock = lock

    assert AsrSession(eng, stream=object()).decode() == ""
    assert lock.used is True


def test_decode_serialize_policy(monkeypatch):
    """CPU 不串行；CUDA 串行；环境变量可强制串行（回滚开关）。"""
    monkeypatch.delenv("IL_ASR_SERIALIZE_DECODE", raising=False)
    assert _decode_must_serialize("cpu") is False
    assert _decode_must_serialize("cuda") is True
    monkeypatch.setenv("IL_ASR_SERIALIZE_DECODE", "1")
    assert _decode_must_serialize("cpu") is True


def test_kws_load_once_under_concurrency(tmp_path, monkeypatch):
    """KWS 并发冷启动同样只构造一次 spotter。

    Concurrent KWS cold starts construct exactly one spotter."""
    from core import config

    d = tmp_path / "kws"
    d.mkdir()
    (d / "tokens.txt").write_text("x", encoding="utf-8")
    for kind in ("encoder", "decoder", "joiner"):
        (d / f"{kind}.onnx").write_bytes(b"x")
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)

    calls: list[int] = []

    def _fake_spotter(**_kw):
        calls.append(1)
        return object()

    fake_utils = types.SimpleNamespace(text2token=lambda words, **_kw: [[1] for _ in words])
    fake = types.SimpleNamespace(
        KeywordSpotter=_fake_spotter,
        utils=fake_utils,
    )
    monkeypatch.setitem(sys.modules, "sherpa_onnx", fake)
    monkeypatch.setitem(sys.modules, "sherpa_onnx.utils", fake_utils)

    eng = KwsEngine(KwsOptions(model_dir=str(d), keywords=("衍衡",)))
    barrier = threading.Barrier(8)
    results: list[tuple[bool, str]] = []

    def worker():
        barrier.wait()
        results.append(eng.status())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results and all(ok for ok, _ in results)
    assert len(calls) == 1
