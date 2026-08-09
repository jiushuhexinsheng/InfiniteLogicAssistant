# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — 主入口

用法:
    python main.py serve             启动 Web 服务
    python main.py test              测试 LLM / ASR 连通性
"""
import asyncio
import base64
import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import (
    ensure_dirs, is_llm_configured, resolve_llm_profile,
    is_asr_configured, resolve_asr_profile,
)
from core.logger import logger

TEST_TIMEOUT = 8  # 连通测试超时（秒）


def cmd_serve():
    from server import start_server
    start_server()


def _silence_wav_base64(seconds: float = 0.3, rate: int = 16000) -> str:
    """生成一小段静音 WAV 的 base64（用于 ASR 连通性测试，无需真实语音）"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return base64.b64encode(buf.getvalue()).decode("utf-8")


async def _test_llm() -> bool:
    """LLM 连通性：stream_chat 消费 done 事件"""
    from core.llm.stream import stream_chat
    _, profile = resolve_llm_profile()
    profile = dict(profile, timeout=TEST_TIMEOUT)  # 测试用短超时
    messages = [
        {"role": "system", "content": "你是一个测试助手。"},
        {"role": "user", "content": "请只回复两个字：连通"},
    ]
    try:
        async for evt in stream_chat(messages, profile=profile):
            if evt["type"] == "done":
                content = (evt["message"].get("content") or "").strip()
                print(f"      回复: {content[:80]}")
                return bool(content)
        return False
    except Exception as e:
        logger.error("LLM 连通性测试失败: {}", e)
        print(f"  [失败] {type(e).__name__}: {e}")
        print("       详情见 data/agent.log")
        return False


async def _test_asr() -> bool:
    """ASR 连通性：静音 WAV base64 过一遍链路"""
    from core.voice import get_asr
    asr = get_asr()
    try:
        audio_b64 = _silence_wav_base64()
        text = await asr.transcribe_base64(audio_b64, "wav")
        ok = isinstance(text, str)
        if ok:
            print(f"      返回: {text.strip()[:80] or '(空文本，链路已通)'}")
        return ok
    except Exception as e:
        logger.error("ASR 连通性测试失败: {}", e)
        print(f"  [失败] {type(e).__name__}: {e}")
        print("       详情见 data/agent.log")
        return False


async def _cmd_test() -> bool:
    """异步测试主体，返回是否全部通过"""
    print("=" * 56)
    print("  连通性测试 — LLM / ASR")
    print("=" * 56)

    failed = False

    # ── LLM ──
    print("\n[LLM] 正在测试...")
    if not is_llm_configured():
        print("  [跳过] LLM 未配置（config.yaml 缺少 endpoint/model）")
    else:
        print(f"  [测试] profile={resolve_llm_profile()[0]}")
        if await _test_llm():
            print("  [OK] LLM 连通正常")
        else:
            failed = True

    # ── ASR ──
    print("\n[ASR] 正在测试...")
    if not is_asr_configured():
        print("  [跳过] ASR 未配置（config.yaml 缺少 endpoint/model）")
    else:
        print(f"  [测试] profile={resolve_asr_profile()[0]}")
        if await _test_asr():
            print("  [OK] ASR 连通正常")
        else:
            failed = True

    print(f"\n{'=' * 56}")
    if failed:
        print("  结果: 存在连通性失败，请查看 data/agent.log")
    else:
        print("  结果: LLM / ASR 连通正常")
    print(f"{'=' * 56}\n")
    return failed


def cmd_test():
    failed = asyncio.run(_cmd_test())
    if failed:
        sys.exit(1)


def main():
    ensure_dirs()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        cmd_serve()
    elif cmd == "test":
        cmd_test()
    else:
        print(f"用法: python main.py {{serve|test}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
