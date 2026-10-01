# -*- coding: utf-8 -*-
"""唤醒链路端点:转写 / 本地 KWS 快检 / 唤醒判定。

Voice wake chain endpoints: transcription / local KWS quick check / wake judgement.

⚠️ 审计(audit)在本模块命名空间 —— 测试补丁点是 `core.api.voice.wake.audit`,
不是 `core.logger.audit`(名字在 import 时绑定进本模块)。
"""
import base64
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import config as config
from core.api.schemas import TextResponse, WakeCheckResponse, WakeResponse
from core.logger import audit, logger

router = APIRouter()


@router.post("/voice/transcribe", response_model=TextResponse)
async def voice_transcribe(request: Request):
    """语音转写：接收 base64 音频 → 返回识别文本。

    ⚠️ **本端点同样会把音频送上云**（作答与指令两条通道都经它，见前端 `transcribeSegment`），
    所以它和 `/voice/wake` 一样逐条写审计 —— 否则「数审计行 = 数上传次数」不成立，
    按 `wake` 行估算成本会**显著偏低**（作答复用这条通道，而那正是使用最频繁的一段）。

    ASR transcription: accept base64 audio and return the recognized text.

    NOTE: this endpoint sends audio to the cloud too (both the answer and the command channels go
    through it — see the frontend's `transcribeSegment`), so it is audited line-by-line just like
    `/voice/wake`. Without that, "count audit lines = count uploads" would not hold and estimating
    cost from `wake` lines alone would come out **far too low** (answering reuses this channel, and
    that is the most frequently used path).

    Args:
        request: FastAPI 请求，JSON 体含 audio_base64。The FastAPI request with
            audio_base64 in the JSON body.

    Returns:
        {"ok": True, "text": ...}，或错误响应。{"ok": True, "text": ...}, or an error response.
    """
    from core.voice import get_asr
    asr = get_asr()
    if not asr.available():
        return JSONResponse({"ok": False, "error": "ASR 未配置"})
    try:
        body = await request.body()
        params = json.loads(body.decode("utf-8"))
        b64 = params.get("audio_base64", "")
        if not b64:
            return JSONResponse({"ok": False, "error": "请提供 audio_base64 参数"})
        text = await asr.transcribe_base64(b64, "wav")
        # 逐条记一次云端上传。前缀 `audio-upload via=` 与 /voice/wake 共用，便于一条 grep 数全：
        #   grep -c 'audio-upload via=' data/audit.log
        # One line per cloud upload. The `audio-upload via=` prefix is shared with /voice/wake so a
        # single grep counts them all.
        audit(f"audio-upload via=transcribe chars={len(text)} text={text[:80]!r}")
        return {"ok": True, "text": text}
    except Exception as e:
        logger.error("voice_transcribe: {}", e)
        return JSONResponse({"ok": False, "error": str(e)})

@router.post("/voice/wake/check", response_model=WakeCheckResponse)
async def voice_wake_check(request: Request):
    """本地 KWS 快检：只回答「这段音频里有没有唤醒词」，毫秒级、不出本机、零云端调用。

    判定与提取分离的前半段：命中 → 前端**立即**提示音 + 进入等指令窗口（动作先行，
    不等任何「二次确认」）；指令文本的提取由完整 /voice/wake 在后台异步完成。

    Local KWS quick check: answers only "does this clip contain a wake word" —
    milliseconds, no cloud call, audio never leaves the machine. First half of
    "verdict first, extraction later": on a hit the frontend acts **immediately**
    (chime + command window) with no re-confirmation; command extraction happens
    asynchronously via the full /voice/wake.
    """
    from core.voice.kws import get_kws

    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    b64 = (params.get("audio_base64") or "").strip()
    if not b64:
        return JSONResponse({"ok": False, "error": "请提供 audio_base64 参数"}, status_code=400)

    try:
        wav_bytes = base64.b64decode(b64)
    except Exception:
        return JSONResponse({"ok": False, "error": "audio_base64 非法"}, status_code=400)
    hit = get_kws().detect_wav_bytes(wav_bytes)  # True命中 / False未命中 / None旁路
    if hit is False:
        audit("kws-gate skip=1")
    elif hit is True:
        audit("kws-gate hit=1")
    return {"ok": True, "hit": hit is True, "bypass": hit is None}

@router.post("/voice/wake", response_model=WakeResponse)
async def voice_wake(request: Request):
    """唤醒检测：接收音频片段 → 转写 → 判定唤醒词 → 切出指令。

    与 /voice/transcribe 分开而不是复用：这一步的产物是**判定**（matched / command），
    不是文本 —— 前端据此决定「直接发起任务」还是「提示音后等指令」，把判定放后端
    可以让它被 pytest 单测，前端保持薄。

    Wake detection: accept an audio clip, transcribe it, judge the wake word and split out the
    command. Kept separate from /voice/transcribe because the product here is a **judgement**
    (matched / command) rather than text: the frontend decides between "start the task now" and
    "chime, then wait for the command", and putting that judgement server-side makes it unit
    testable while keeping the frontend thin.
    """
    from core.voice import get_asr
    from core.voice.kws import get_kws
    from core.voice.wake import detect

    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    b64 = (params.get("audio_base64") or "").strip()
    if not b64:
        return JSONResponse({"ok": False, "error": "请提供 audio_base64 参数"}, status_code=400)

    # 本地 KWS 前置闸门：未命中直接丢弃，不上云（背景媒体声/闲聊不花钱、不出本机）。
    # mode=cloud 显式旁路闸门（用户要纯云端判定，最大召回）。审计用独立前缀
    # `kws-gate skip=`：它不是云端上传，不得混入 `audio-upload via=` 成本口径。
    # Local KWS pre-gate: misses are dropped without any cloud call (background media
    # and chatter cost nothing and never leave the machine). mode=cloud explicitly
    # bypasses the gate (pure cloud judging, maximum recall). Audited under its own
    # `kws-gate skip=` prefix: it is NOT a cloud upload and must not pollute the
    # `audio-upload via=` cost accounting.
    wav_bytes = base64.b64decode(b64)
    kws_hit: bool | None = None
    if params.get("mode") != "cloud":
        kws_hit = get_kws().detect_wav_bytes(wav_bytes)  # True命中 / False未命中 / None旁路
        if kws_hit is False:
            audit("kws-gate skip=1")
            return {"ok": True, "matched": False, "command": "", "text": ""}

    asr = get_asr()
    if not asr.available():
        return JSONResponse({"ok": False, "error": "ASR 未配置"})
    try:
        text = await asr.transcribe_base64(b64, "wav")
    except Exception as e:
        logger.error("voice_wake: {}", e)
        # 不吞异常：前端要靠 ok=False 计连续失败次数并熔断，静默成功会让它一直重试。
        # Do not swallow: the frontend counts ok=False toward its circuit breaker; a silent success
        # would keep it retrying.
        return JSONResponse({"ok": False, "error": str(e)})

    result = detect(text, config.settings.voice.wake_word.keywords)
    # 音频判定优先于文本判定：KWS（发音级）听到了唤醒词就唤醒成立，ASR 文本只负责
    # 切指令 —— 文本判不中（ASR 把词写飞）时按「仅唤醒」处理（command 空 → 提示音 +
    # 等指令），不能把一次真实唤醒丢掉。反之文本判中而 KWS 未中（闸门旁路时）照常成立。
    # Audio verdict beats text verdict: once KWS (pronunciation level) heard the wake
    # word, the wake stands and the ASR text only splits out the command. When the text
    # judge misses (ASR wrote the word wildly), fall back to "wake only" (empty command
    # → chime + wait for the command) instead of dropping a real wake. Conversely, a
    # text hit with no KWS hit (gate bypassed) stands as usual.
    matched = result.matched or kws_hit is True
    command = result.command if result.matched else ""
    # 每次上传记一笔：这是统计调用量与成本的依据（spec「成本与隐私」）。前缀与
    # /voice/transcribe 共用，`grep -c 'audio-upload via=' data/audit.log` 即云端上传总次数。
    # One audit line per upload: the basis for measuring call volume and cost (spec, "cost and
    # privacy"). The prefix is shared with /voice/transcribe, so a single grep counts every cloud
    # upload.
    audit(
        f"audio-upload via=wake matched={matched} chars={len(text)} "
        f"command={command[:40]!r} text={text[:80]!r}"
    )
    return {"ok": True, "matched": matched, "command": command, "text": result.text}
