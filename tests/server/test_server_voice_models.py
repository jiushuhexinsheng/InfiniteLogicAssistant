# -*- coding: utf-8 -*-
"""模型自检缓存键：必须绑定到具体模型，换模型后不能复用旧自检结论。

Model self-test cache keying: results must be bound to the specific model so switching
models cannot reuse the previous model's verdict inside the TTL.
"""
import time

from core import config
from core.api.voice import models as models_api


def test_health_cache_key_tracks_model(monkeypatch):
    """换模型 → 键不同；旧键的结果不会被新模型读到。
    Switching models changes the key; the old result is not read for the new model."""
    monkeypatch.setattr(config.settings.voice.asr, "local_model", "models/asr/a")
    key_a = models_api._health_key("asr")
    models_api._HEALTH[key_a] = {"ok": True, "ready": True, "at": time.time()}
    assert models_api._get_health("asr") is not None

    monkeypatch.setattr(config.settings.voice.asr, "local_model", "models/asr/b")
    assert models_api._health_key("asr") != key_a
    assert models_api._get_health("asr") is None


def test_health_cache_respects_ttl(monkeypatch):
    """过期条目不再生效。Expired entries stop applying."""
    monkeypatch.setattr(config.settings.voice.vad, "model", "models/vad/x.onnx")
    models_api._HEALTH[models_api._health_key("vad")] = {
        "ok": True, "ready": True, "at": time.time() - models_api._HEALTH_TTL_S - 1,
    }
    assert models_api._get_health("vad") is None
