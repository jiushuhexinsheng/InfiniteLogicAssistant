# -*- coding: utf-8 -*-
"""ASR 三模式分发：local 绝不静默上云、hybrid 兜底、cloud 不触碰本地、to_thread 卸载。

ASR tri-mode dispatch: `local` never silently uploads, `hybrid` falls back, `cloud` never
touches the local engine, and the local decode is offloaded to a worker thread."""
import asyncio
import threading

import pytest

from core.voice import asr_dispatch


class _FakeLocal:
    def __init__(self, text="", available=True, reason="本地不可用", boom=None):
        self.text = text
        self._available = available
        self._reason = reason
        self.boom = boom
        self.calls = 0
        self.thread_ids: list[int] = []

    def available(self) -> bool:
        return self._available

    def status(self):
        return (True, "") if self._available else (False, self._reason)

    def transcribe_wav(self, wav: bytes) -> str:
        self.calls += 1
        self.thread_ids.append(threading.get_ident())
        if self.boom is not None:
            raise self.boom
        return self.text


class _FakeCloud:
    def __init__(self, text="cloud-text", available=True):
        self.text = text
        self._available = available
        self.calls = 0

    def available(self) -> bool:
        return self._available

    async def transcribe_base64(self, b64: str, fmt: str = "wav") -> str:
        self.calls += 1
        return self.text


class _ExplodingCloud:
    """云端桩：任何调用即 AssertionError —— 用来证明「绝不静默上云」的硬证据。"""

    def available(self) -> bool:
        raise AssertionError("云端不该被调用（local 模式绝不静默上云）")

    async def transcribe_base64(self, *a, **k) -> str:  # pragma: no cover - 不该被调到
        raise AssertionError("云端不该被调用（local 模式绝不静默上云）")


class _ExplodingLocal:
    """本地桩：任何调用即 AssertionError —— 证明 cloud 模式不触碰本地引擎。"""

    def available(self) -> bool:
        raise AssertionError("本地引擎不该被调用（cloud 模式）")

    def status(self):  # pragma: no cover - 不该被调到
        raise AssertionError("本地引擎不该被调用（cloud 模式）")

    def transcribe_wav(self, wav):  # pragma: no cover - 不该被调到
        raise AssertionError("本地引擎不该被调用（cloud 模式）")


def _patch(monkeypatch, mode, local=None, cloud=None):
    from core import config
    monkeypatch.setattr(config.settings.voice.asr, "mode", mode)
    if local is not None:
        monkeypatch.setattr(asr_dispatch, "_local", lambda: local)
    if cloud is not None:
        monkeypatch.setattr(asr_dispatch, "_cloud", lambda: cloud)


def test_resolve_mode_defaults_and_valid(monkeypatch):
    assert asr_dispatch.resolve_mode() == "cloud"  # 默认
    _patch(monkeypatch, "hybrid")
    assert asr_dispatch.resolve_mode() == "hybrid"
    _patch(monkeypatch, "bogus")  # schema 之外的值 → 回落 cloud + 告警
    assert asr_dispatch.resolve_mode() == "cloud"


def test_cloud_mode_never_touches_local(monkeypatch):
    """cloud 模式：本地引擎零调用（也即零加载）。"""
    cloud = _FakeCloud(text="hello")
    _patch(monkeypatch, "cloud", local=_ExplodingLocal(), cloud=cloud)
    res = asyncio.run(asr_dispatch.transcribe(b"wav", via="wake"))
    assert res == asr_dispatch.AsrResult("hello", engine="cloud")
    assert cloud.calls == 1


def test_cloud_mode_raises_when_unconfigured(monkeypatch):
    _patch(monkeypatch, "cloud", local=_ExplodingLocal(), cloud=_FakeCloud(available=False))
    with pytest.raises(asr_dispatch.AsrUnavailableError) as ei:
        asyncio.run(asr_dispatch.transcribe(b"wav", via="wake"))
    assert ei.value.code == "cloud_unavailable"
    assert "ASR" in str(ei.value)  # 端点/测试依赖错误串含 "ASR"


def test_local_mode_uses_local_and_never_uploads(monkeypatch):
    """local 模式：走本地、云端零调用 —— 隐私不变量的硬证据。"""
    local = _FakeLocal(text="本地文本")
    _patch(monkeypatch, "local", local=local, cloud=_ExplodingCloud())
    res = asyncio.run(asr_dispatch.transcribe(b"wav", via="wake"))
    assert res == asr_dispatch.AsrResult("本地文本", engine="local")
    assert local.calls == 1


def test_local_mode_missing_model_raises_and_never_uploads(monkeypatch):
    """local 模式缺模型：明确抛错，云端**零调用**（绝不静默上云）。"""
    local = _FakeLocal(available=False, reason="本地 ASR 模型目录不存在")
    _patch(monkeypatch, "local", local=local, cloud=_ExplodingCloud())
    with pytest.raises(asr_dispatch.AsrUnavailableError) as ei:
        asyncio.run(asr_dispatch.transcribe(b"wav", via="wake"))
    assert ei.value.code == "local_unavailable"
    assert ei.value.engine == "local"
    assert "模型目录不存在" in str(ei.value)


def test_hybrid_prefers_local_without_upload(monkeypatch):
    local = _FakeLocal(text="本地命中")
    cloud = _FakeCloud()
    _patch(monkeypatch, "hybrid", local=local, cloud=cloud)
    res = asyncio.run(asr_dispatch.transcribe(b"wav", via="call-segment"))
    assert res.engine == "local" and res.fallback is False
    assert cloud.calls == 0


def test_hybrid_empty_local_falls_back_to_cloud(monkeypatch):
    """hybrid：本地转写为空（合法结果，但按用户裁定算「不可用」）→ 云端兜底并标 fallback。"""
    cloud = _FakeCloud(text="云端文本")
    _patch(monkeypatch, "hybrid", local=_FakeLocal(text="   "), cloud=cloud)
    res = asyncio.run(asr_dispatch.transcribe(b"wav", via="wake"))
    assert res == asr_dispatch.AsrResult("云端文本", engine="cloud", fallback=True)
    assert cloud.calls == 1


def test_hybrid_unavailable_local_falls_back_to_cloud(monkeypatch):
    cloud = _FakeCloud(text="云端文本")
    _patch(monkeypatch, "hybrid", local=_FakeLocal(available=False), cloud=cloud)
    res = asyncio.run(asr_dispatch.transcribe(b"wav", via="wake"))
    assert res.engine == "cloud" and res.fallback is True


def test_hybrid_local_exception_falls_back_to_cloud(monkeypatch):
    """hybrid：本地抛错也走云端兜底（漏斗契约要求本地失败不炸整条链）。"""
    cloud = _FakeCloud(text="云端文本")
    _patch(monkeypatch, "hybrid",
           local=_FakeLocal(boom=RuntimeError("decode boom")), cloud=cloud)
    res = asyncio.run(asr_dispatch.transcribe(b"wav", via="wake"))
    assert res.engine == "cloud" and res.fallback is True


def test_local_decode_runs_off_main_thread(monkeypatch):
    """`to_thread` 证据：本地解码不在主线程跑（否则会阻塞事件循环）。"""
    local = _FakeLocal(text="ok")
    _patch(monkeypatch, "local", local=local, cloud=_ExplodingCloud())
    main_id = threading.get_ident()
    asyncio.run(asr_dispatch.transcribe(b"wav", via="wake"))
    assert local.thread_ids and local.thread_ids[0] != main_id
