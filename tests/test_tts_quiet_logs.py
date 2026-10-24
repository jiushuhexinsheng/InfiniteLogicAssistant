# -*- coding: utf-8 -*-
"""本地 TTS 原生日志开关：Kokoro 的 C++ 诊断（重复词条/未知 token/跳过的音素）
直写 stderr，sherpa-onnx 没有日志级别 API，只能在子进程里关掉 fd 2。

Local TTS native-log switch: Kokoro's C++ diagnostics (duplicate lexicon entries,
unknown tokens, skipped phonemes) go straight to stderr and sherpa-onnx exposes no
log-level API, so the child process redirects fd 2 to the null device.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from core.config.schema import TtsSection

ROOT = Path(__file__).resolve().parent.parent


def test_quiet_native_logs_defaults_on():
    """默认关闭原生噪声；仍可显式设为 False 以便调试。On by default, can be disabled."""
    assert TtsSection().quiet_native_logs is True
    assert TtsSection(quiet_native_logs=False).quiet_native_logs is False


def test_native_stderr_silencer_discards_writes():
    """静音后子进程写 stderr 的内容不应到达父进程的捕获管道。
    After silencing, stderr writes in the child never reach the parent's capture."""
    code = (
        "import sys\n"
        "from core.voice.tts import _silence_native_stderr\n"
        "_silence_native_stderr()\n"
        "print('NATIVE-NOISE', file=sys.stderr)\n"
        "print('DONE')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "NATIVE-NOISE" not in proc.stderr
    assert "DONE" in proc.stdout


def test_worker_silences_stderr_unless_disabled(monkeypatch):
    """quiet=True 时子进程入口先静音；quiet=False 时保留原生输出。
    The child entry silences first when quiet; quiet=False keeps native output."""
    from core.voice import tts as tts_mod

    hits: list[bool] = []
    monkeypatch.setattr(tts_mod, "_silence_native_stderr", lambda: hits.append(True))

    class _Engine:
        def synthesize_wav(self, _text: str) -> bytes:
            return b"wav"

    monkeypatch.setattr(tts_mod, "_worker_engine", _Engine())
    monkeypatch.setattr(tts_mod, "_worker_opts", {"model_dir": "x"})

    assert tts_mod._tts_worker({"model_dir": "x"}, "你好") == b"wav"
    assert hits == [True]

    hits.clear()
    assert tts_mod._tts_worker({"model_dir": "x"}, "你好", quiet=False) == b"wav"
    assert hits == []


@pytest.mark.asyncio
async def test_synthesize_passes_config_flag(monkeypatch):
    """_synthesize_local 把配置里的开关传给子进程（用户可关掉静音）。
    _synthesize_local forwards the configured switch to the child."""
    from core import config
    from core.voice import tts as tts_mod

    captured: dict[str, object] = {}

    def fake_worker(opts, text, quiet=True):
        captured["quiet"] = quiet
        return b"wav"

    monkeypatch.setattr(tts_mod, "_tts_worker", fake_worker)
    monkeypatch.setattr(tts_mod, "_get_tts_pool", lambda: None)
    monkeypatch.setattr(config.settings.voice.tts, "quiet_native_logs", False)

    wav, media = await tts_mod._synthesize_local("你好")
    assert (wav, media) == (b"wav", "audio/wav")
    assert captured["quiet"] is False
