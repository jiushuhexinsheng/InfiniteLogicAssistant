# -*- coding: utf-8 -*-
"""voice 域 API — 配置 / TTS / ASR 转写 / 编排 SSE 入口（唯一 agent 路径）

voice domain API — config / TTS / ASR transcription / orchestration SSE entry
(the only agent path)
"""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from core import config as config
from core.api import state
from core.api.schemas import (
    AckResponse,
    ApiResponse,
    ConfigResponse,
    PingResponse,
    TextResponse,
    WakeResponse,
)
from core.orchestrator.events import DoneEvent, ErrorEvent
from core.logger import audit, logger

router = APIRouter()


def _sse(payload: dict) -> str:
    """把事件 dict 编码为一条 SSE 消息（data: <json>\\n\\n）。

    Encode an event dict into a single SSE message (data: <json>\\n\\n).

    Args:
        payload: 事件数据。The event data.

    Returns:
        SSE 格式字符串。The SSE-formatted string.
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/ping", response_model=PingResponse)
async def ping():
    """心跳：返回当前服务器时间。

    Heartbeat: return the current server time.

    Returns:
        {"ok": True, "time": ISO 时间戳}。{"ok": True, "time": ISO timestamp}.
    """
    from datetime import datetime
    return {"ok": True, "time": datetime.now().isoformat()}


@router.get("/config", response_model=ConfigResponse)
async def config_endpoint():
    """返回前端启动所需的语音/模型配置快照（可用性 + 当前 profile + 语音参数）。

    Return the voice/model config snapshot needed by the frontend on startup
    (availability + current profile + voice parameters).

    Returns:
        配置字典。The config dict.
    """
    return {
        "llm_available": config.is_llm_configured(),
        "llm_profile": config.resolve_llm_profile()[0],
        "asr_available": config.is_asr_configured(),
        "asr_profile": config.resolve_asr_profile()[0],
        "tts_available": config.is_tts_enabled(),
        "tts_profile": config.resolve_tts_profile()[0],
        "tts_voice": config.resolve_tts_profile()[1].get("voice", ""),
        "tts_model": config.resolve_tts_profile()[1].get("model", ""),
        "wake_word": config.settings.voice.wake_word.model_dump(),
        "vad": config.settings.voice.vad.model_dump(),
    }


@router.post("/tts")
async def tts_synthesize(request: Request):
    """文本转语音：调后端配置的 OpenAI 兼容 TTS 端点，返回音频字节。

    请求体：{"text": "...", "voice": "可选，缺省用配置里的 voice"}

    Text-to-speech: call the backend-configured OpenAI-compatible TTS endpoint and
    return the audio bytes. Request body: {"text": "...", "voice": "optional,
    defaults to the voice from config"}
    """
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    text = (params.get("text") or "").strip()
    voice = params.get("voice") or None
    if not text:
        return JSONResponse({"ok": False, "error": "text 不能为空"}, status_code=400)
    if not config.is_tts_enabled():
        return JSONResponse(
            {"ok": False, "error": "TTS 未启用：voice.tts.enabled=false 或未配置 endpoint"},
            status_code=400,
        )
    try:
        from core.voice.tts import synthesize
        from core.voice.tts import TtsConfigError
        audio, media_type = await synthesize(text, voice)
    except TtsConfigError as e:
        # 配置问题（未启用/缺 voice_ref 等）：客户端可修复 → 400
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        logger.warning("TTS 合成失败: {}", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return Response(content=audio, media_type=media_type)


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
    from core.voice.wake import detect

    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    b64 = (params.get("audio_base64") or "").strip()
    if not b64:
        return JSONResponse({"ok": False, "error": "请提供 audio_base64 参数"}, status_code=400)

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
    # 每次上传记一笔：这是统计调用量与成本的依据（spec「成本与隐私」）。前缀与
    # /voice/transcribe 共用，`grep -c 'audio-upload via=' data/audit.log` 即云端上传总次数。
    # One audit line per upload: the basis for measuring call volume and cost (spec, "cost and
    # privacy"). The prefix is shared with /voice/transcribe, so a single grep counts every cloud
    # upload.
    audit(
        f"audio-upload via=wake matched={result.matched} chars={len(text)} "
        f"command={result.command[:40]!r} text={text[:80]!r}"
    )
    return {"ok": True, "matched": result.matched, "command": result.command, "text": result.text}


@router.post("/voice/utter")
async def voice_utter(request: Request):
    """编排入口：文本(语音转写后/文字输入) → SSE 事件流。

    事件：task_state / content_delta / question / error / done。
    question 事件后需操作者回答：POST /api/voice/answer {session_id, text}。
    请求体可带 session_id：续接已有会话（加载其历史作为多轮种子）。

    Orchestration entry: text (post-ASR or typed input) → SSE event stream. Events:
    task_state / content_delta / question / error / done. After a question event the
    operator must answer via POST /api/voice/answer {session_id, text}. The request
    body may carry session_id to resume an existing session (loading its history as
    the multi-turn seed).
    """
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import run_pipeline
    from core.orchestrator.session import Session
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    text = (params.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "缺少 text 参数"}, status_code=400)
    messages = params.get("messages")
    if not isinstance(messages, list):
        messages = None
    # 模式：task = 完成后询问并存档；其余（含缺失/非法）一律 chat（向后兼容老前端）。
    # Mode: "task" asks and archives on completion; anything else (missing or invalid) is
    # "chat" for backward compatibility.
    mode = "task" if params.get("mode") == "task" else "chat"

    session = Session()
    session_id = params.get("session_id")
    if isinstance(session_id, str) and session_id:
        # 该会话正阻塞在 ask()：拒绝本次 utter。否则会新建 Session 覆盖注册表，
        # 旧的 ask() 将永久挂死（前端 runTurn 也会 abort 掉那条流）。
        # 前端路由正确时走不到这里；它防的是前端出 bug 或有人直接打 API。
        # The session is blocked in ask(): reject this utter. Otherwise a fresh Session
        # would overwrite the registry and the old ask() would hang forever (the
        # frontend's runTurn would also abort that stream). Correct frontend routing never
        # reaches this branch; it guards against a frontend bug or a direct API call.
        busy = state.get_session(session_id)
        busy_channel = getattr(busy, "channel", None) if busy else None
        if busy_channel is not None and getattr(busy_channel, "awaiting_answer", False):
            return JSONResponse(
                {"ok": False, "error": "该会话正在等待回答，请先作答或新建会话"},
                status_code=409,
            )
        # 续接已有会话：固定 id；请求未带历史种子时从存储加载
        session = Session(session_id=session_id)
        if messages is None:
            try:
                from core.session.history import get_history_store
                conv = await get_history_store().get_conversation(session_id)
                if conv and conv.get("messages"):
                    messages = [
                        {"role": m["role"], "content": m["content"]}
                        for m in conv["messages"]
                        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
                    ]
            except Exception:
                pass
    controller = StopController()
    state.register(session, controller)
    events: asyncio.Queue = asyncio.Queue()
    runner = asyncio.ensure_future(
        run_pipeline(text, session, events, controller, messages=messages, mode=mode))

    async def event_stream():
        """SSE 事件流生成器：转发队列事件，处理 runner 异常兜底并做收尾清理。

        SSE event stream generator: forward queued events, fall back on runner
        exceptions, and do final cleanup.
        """
        getter = asyncio.ensure_future(events.get())
        try:
            while True:
                done, _ = await asyncio.wait({runner, getter}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    evt = getter.result()
                    yield _sse(evt)
                    if evt["type"] == "done":
                        break
                    getter = asyncio.ensure_future(events.get())  # 取下一个事件
                if runner in done:
                    # runner 提前结束（异常兜底），避免客户端永久等待
                    if not events.empty():
                        continue
                    exc = runner.exception()
                    if exc is not None:
                        yield _sse(ErrorEvent(message=f"编排异常: {exc}").emit())
                    yield _sse(DoneEvent().emit())
                    break
        finally:
            getter.cancel()
            runner.cancel()
            await asyncio.gather(getter, runner, return_exceptions=True)
            await state.persist(session, state.session_ts.get(session.id))
            state.cleanup(session.id)  # done/error/客户端断开时不再被引用

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/voice/answer", response_model=ApiResponse)
async def voice_answer(request: Request):
    """投递操作者对澄清/确认问题的回答，解除 pipeline 的 ask() 阻塞。

    Deliver the operator's answer to a clarification/confirmation question,
    unblocking the pipeline's ask().
    """
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    session = state.get_session(params.get("session_id", ""))
    channel = getattr(session, "channel", None) if session else None
    if channel is None:
        return JSONResponse({"ok": False, "error": "会话不存在或未在等待回答"}, status_code=404)
    # choice 为结构化选择的取值（前端按钮回传）。此处只做「非空字符串」的形状校验，
    # 取值合法性由消费方（如权限策略层）自行判断 —— 这样新增选项集（允许一次 /
    # 永久允许 / 拒绝 …）无需改动本端点。
    #
    # choice carries the structured selection returned by the frontend's buttons. Only its
    # shape (a non-empty string) is validated here; whether a value is meaningful is up to
    # the consumer (e.g. the permission policy layer), so new option sets need no change here.
    raw_choice = params.get("choice")
    choice = raw_choice.strip() if isinstance(raw_choice, str) and raw_choice.strip() else None
    channel.answer(str(params.get("text") or ""), choice)
    return {"ok": True}


@router.post("/task/{session_id}/stop", response_model=AckResponse)
async def task_stop(session_id: str):
    """停止该会话的整个任务（CancellationToken → executor/子进程中止）。

    Stop the whole task of the session (CancellationToken → executor/subprocess abort).
    """
    ctrl = state.get_controller(session_id)
    if ctrl:
        ctrl.stop_task()
    return {"ok": True, "ack": "stop"}
