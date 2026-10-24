# -*- coding: utf-8 -*-
"""本地引擎加载失败的缓存语义：失败不得永久缓存（模型补装/瞬时错误后可自愈）。

Local engine load-failure caching semantics: failures must not be cached forever, so
a later session retries after the model is installed or a transient error clears.
"""

from core.voice.local.sherpa_onnx.asr import AsrOptions, StreamingAsrEngine
from core.voice.local.sherpa_onnx.kws import KwsEngine, KwsOptions
from core.voice.local.sherpa_onnx.tts import TtsEngine, TtsOptions
from core.voice.local.sherpa_onnx.vad import VadEngine, VadOptions


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
