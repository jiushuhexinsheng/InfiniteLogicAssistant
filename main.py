# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — 主入口

用法:
    python main.py serve             启动 Web 服务
    python main.py test              测试 LLM / ASR 连通性
"""
import base64
import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import ensure_dirs, is_llm_configured, resolve_llm_profile, is_asr_configured, resolve_asr_profile
from core.logger import logger


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


def cmd_test():
    """测试 LLM / ASR 连通性（start.bat 启动前调用）。

    任一失败返回非零退出码，便于启动脚本中断并提示查看 data/agent.log。
    """
    import traceback
    TEST_TIMEOUT = 8  # 连通测试超时（秒），避免服务不可达时长时间阻塞启动
    print("=" * 56)
    print("  连通性测试 — LLM / ASR")
    print("=" * 56)

    failed = False

    # ── LLM ──
    print("\n[LLM] 正在测试...")
    if not is_llm_configured():
        print("  [跳过] LLM 未配置（config.yaml 缺少 endpoint/model）")
    else:
        try:
            from core.llm import get_llm
            llm = get_llm()
            llm.timeout = TEST_TIMEOUT  # 测试用短超时，不改变 config.yaml 的生产配置
            reply = llm.chat("你是一个测试助手。", "请只回复两个字：连通")
            ok = bool(reply and reply.strip())
            print(f"  [{'OK' if ok else '失败'}] profile={llm.profile_name} provider={llm.provider} model={llm.model}")
            if ok:
                print(f"      回复: {reply.strip()[:80]}")
            else:
                print("      返回为空")
                failed = True
        except Exception as e:
            logger.error("LLM 连通性测试失败: {}", e)
            logger.debug("LLM 测试堆栈:\n{}", traceback.format_exc())
            print(f"  [失败] {type(e).__name__}: {e}")
            print("       详情见 data/agent.log")
            failed = True

    # ── ASR ──
    print("\n[ASR] 正在测试...")
    if not is_asr_configured():
        print("  [跳过] ASR 未配置（config.yaml 缺少 endpoint/model）")
    else:
        try:
            from core.voice import get_asr
            asr = get_asr()
            asr.timeout = TEST_TIMEOUT  # 测试用短超时
            audio_b64 = _silence_wav_base64()
            text = asr.transcribe_base64(audio_b64, "wav")
            ok = isinstance(text, str)
            print(f"  [{'OK' if ok else '失败'}] profile={asr.profile_name} provider={asr.provider} model={asr.model}")
            if ok:
                print(f"      返回: {text.strip()[:80] or '(空文本，链路已通)'}")
            else:
                failed = True
        except Exception as e:
            logger.error("ASR 连通性测试失败: {}", e)
            logger.debug("ASR 测试堆栈:\n{}", traceback.format_exc())
            print(f"  [失败] {type(e).__name__}: {e}")
            print("       详情见 data/agent.log")
            failed = True

    print(f"\n{'=' * 56}")
    if failed:
        print("  结果: 存在连通性失败，请查看 data/agent.log")
        sys.exit(1)
    else:
        print("  结果: LLM / ASR 连通正常")
    print(f"{'=' * 56}\n")


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
