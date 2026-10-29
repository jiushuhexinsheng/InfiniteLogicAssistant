# -*- coding: utf-8 -*-
"""本地语音预热：只热配置启用的引擎、单引擎失败不影响其他、可整体关闭。

Local voice warmup: only configured local engines are warmed, one failure never stops
the others, and the whole thing can be disabled with ``IL_NO_VOICE_WARMUP``.
"""
from __future__ import annotations

from core import config
from core.voice.warmup import start_voice_warmup, warm_local_voice, warmup_disabled


class _FakeEngine:
    """记录 status/create_stream 调用的引擎桩。Engine stub recording calls."""

    def __init__(self, calls: list[str], name: str, *, fail: bool = False) -> None:
        self.calls = calls
        self.name = name
        self.fail = fail

    def status(self) -> tuple[bool, str]:
        self.calls.append(self.name)
        if self.fail:
            raise RuntimeError(f"{self.name} boom")
        return True, ""

    def create_stream(self):
        self.calls.append(f"{self.name}:stream")
        return object()


class _FakeRuntime:
    def __init__(self, calls: list[str], *, fail: set[str] | None = None) -> None:
        fail = fail or set()
        self._vad = _FakeEngine(calls, "vad", fail="vad" in fail)
        self._kws = _FakeEngine(calls, "kws", fail="kws" in fail)
        self._asr = _FakeEngine(calls, "asr", fail="asr" in fail)
        self._tts = _FakeEngine(calls, "tts", fail="tts" in fail)

    def vad(self):
        return self._vad

    def kws(self):
        return self._kws

    def asr(self):
        return self._asr

    def tts(self):
        return self._tts


def _pin(monkeypatch, *, vad: str = "local", kws_enabled: bool = True,
         kws_mode: str = "local", asr: str = "local", tts: str = "local") -> None:
    v = config.settings.voice
    monkeypatch.setattr(v.vad, "mode", vad)
    monkeypatch.setattr(v.kws, "enabled", kws_enabled)
    monkeypatch.setattr(v.kws, "mode", kws_mode)
    monkeypatch.setattr(v.asr, "mode", asr)
    monkeypatch.setattr(v.tts, "mode", tts)


def test_warms_only_configured_local_engines(monkeypatch):
    """cloud ASR / api TTS / 关闭的 KWS 不预热；本地 VAD/KWS 各加载一次。

    Cloud ASR / API TTS / disabled KWS are skipped; local VAD/KWS load once."""
    _pin(monkeypatch, asr="cloud", tts="api", kws_enabled=False)
    calls: list[str] = []
    tts_calls: list[int] = []

    report = warm_local_voice(_FakeRuntime(calls), tts_warm=lambda: tts_calls.append(1))

    assert calls == ["vad", "vad:stream"]
    assert tts_calls == []
    assert report == {"vad": "ok"}
    assert "asr" not in report and "tts" not in report and "kws" not in report


def test_local_tts_is_warmed(monkeypatch):
    """tts.mode=local 时调用注入的 TTS 预热钩子。"""
    _pin(monkeypatch, asr="cloud", kws_enabled=False)
    calls: list[str] = []
    tts_calls: list[int] = []

    report = warm_local_voice(_FakeRuntime(calls), tts_warm=lambda: tts_calls.append(1))

    assert tts_calls == [1]
    assert report["tts"] == "ok"


def test_one_engine_failure_does_not_stop_others(monkeypatch):
    """单个引擎抛错只把该引擎标 error，其余照常预热、不向外抛。

    One engine raising only marks that engine as error; the rest still warm and nothing
    escapes to the caller."""
    _pin(monkeypatch, asr="local", tts="api")
    calls: list[str] = []

    report = warm_local_voice(_FakeRuntime(calls, fail={"asr"}))

    assert report["vad"] == "ok"
    assert report["kws"] == "ok"
    assert report["asr"].startswith("error:")
    assert "vad" in calls and "kws" in calls


def test_disable_env(monkeypatch):
    """IL_NO_VOICE_WARMUP=1 → 不启动线程。"""
    monkeypatch.setenv("IL_NO_VOICE_WARMUP", "1")
    assert warmup_disabled() is True
    assert start_voice_warmup() is None
