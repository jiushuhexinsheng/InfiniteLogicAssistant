# -*- coding: utf-8 -*-
"""voice 域 API — 配置 / TTS / ASR 转写 / 编排 SSE 入口（唯一 agent 路径）

voice domain API — config / TTS / ASR transcription / orchestration SSE entry
(the only agent path)
"""
import asyncio
import base64
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
    WakeCheckResponse,
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
                    # 恢复含块结构（blocks/turn_id/ts 透传）
                    # Restore with block structure (blocks/turn_id/ts pass through).
                    messages = [
                        {"role": m["role"], "content": m["content"],
                         "blocks": m.get("blocks"), "turn_id": m.get("turn_id"), "ts": m.get("ts")}
                        for m in conv["messages"]
                        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
                    ]
            except Exception:
                pass
    controller = StopController()
    # ── 同 id 旧运行取代（docs/designs/06）：新回合先收尾旧 runner（含其断线宽限），
    #    否则宽限机制会让旧管线多跑 resume_grace_s 才停 —— 与前端 runTurn abort 对齐。
    # Same-id supersede (docs/designs/06): a new turn retires the old runner first
    # (including its disconnect grace), otherwise the grace would keep the old pipeline
    # alive for resume_grace_s — aligned with the frontend's runTurn abort.
    old_run = state.get_run(session.id)
    if old_run is not None:
        await _retire_run(old_run)
    state.register(session, controller)
    events: asyncio.Queue = asyncio.Queue()
    runner = asyncio.ensure_future(
        run_pipeline(text, session, events, controller, messages=messages, mode=mode))
    run = state.RunHandle(
        run_id=f"run_{session.id}", session=session, controller=controller,
        events=events, runner=runner,
    )
    state.set_run(session.id, run)

    return StreamingResponse(_stream_run(run), media_type="text/event-stream")


# ── SSE 运行流（首连与 resume 共用）+ 断线宽限（docs/designs/06）──

PING_INTERVAL_S = 15  # 空闲保活间隔（秒）。Idle keep-alive interval (seconds).


async def _retire_run(run: state.RunHandle) -> None:
    """收尾一次运行：停 runner、落盘、（若注册表仍是它）清注册。幂等。

    Wrap up a run: stop the runner, persist, and clear the registry (when it still
    points at this run). Idempotent.

    Args:
        run: 运行句柄。The run handle.
    """
    if run.closed:  # 同步护栏：事件循环单线程，检查与置位之间无 await。
        return      # Sync guard: single-threaded event loop, no await in between.
    run.closed = True
    # 不 cancel 当前任务自己：宽限看门狗到期时正是它在调用本函数，
    # 自 cancel 会让下一个 await 抛 CancelledError、cleanup 中断在半路。
    # Never cancel the current task itself: on grace expiry the watchdog IS the caller,
    # and self-cancellation raises CancelledError at the next await, aborting cleanup halfway.
    if (run.grace_task is not None and not run.grace_task.done()
            and run.grace_task is not asyncio.current_task()):
        run.grace_task.cancel()
    if not run.runner.done():
        run.runner.cancel()
    await asyncio.gather(run.runner, return_exceptions=True)
    await state.persist(run.session, state.session_ts.get(run.session.id))
    if state.get_run(run.session.id) is run:
        state.cleanup(run.session.id)  # 新 run 已顶替时不碰新注册表。Never touch a successor's registry.


def _arm_grace(run: state.RunHandle) -> None:
    """断线进入宽限：runner 继续跑，到期仍未重连则收尾（fail-closed 落盘）。

    `server.resume_grace_s=0` → 立即收尾（旧行为：断线即取消）。

    On disconnect, enter the grace window: the runner keeps going; if no reconnect
    arrives in time, wrap up (fail-closed with persistence). `server.resume_grace_s=0`
    wraps up immediately (legacy behaviour: disconnect cancels).
    """
    grace = getattr(config.settings.server, "resume_grace_s", 120) or 0
    if grace <= 0:
        asyncio.ensure_future(_retire_run(run))
        return

    async def _watchdog() -> None:
        await asyncio.sleep(grace)
        run.grace_task = None  # 先摘掉自己：_retire_run 不再视其为待取消任务。
        if run.closed or run.connected:
            return  # 已重连或已正常收尾。Reconnected or already wrapped up.
        logger.info("run {} 宽限期到期未重连，收尾", run.run_id)
        await _retire_run(run)

    run.grace_task = asyncio.ensure_future(_watchdog())


async def _stream_run(run: state.RunHandle):
    """编排事件 → SSE（唯一 seq 编号与 buffer 入口；空闲 15s 发 ping 保活）。

    首连与 /voice/resume 挂接共用。断线且未完成 → 进宽限；完成 → 收尾。

    Orchestration events → SSE (the single seq-numbering and buffer entry; pings
    every 15s while idle). Shared by the first connection and the /voice/resume
    attach. Disconnected while unfinished → grace; finished → wrap-up.
    """
    getter = asyncio.ensure_future(run.events.get())
    try:
        while True:
            completed, _ = await asyncio.wait(
                {run.runner, getter}, timeout=PING_INTERVAL_S,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not completed:
                # 保活：仅心跳，不占 seq、不进 buffer（重连只需真实事件）。
                # Keep-alive: heartbeat only — no seq, no buffer entry (reconnect only
                # needs real events).
                yield _sse({"type": "ping"})
                continue
            if getter in completed:
                evt = getter.result()
                evt["seq"] = run.next_seq
                run.next_seq += 1
                run.buffer.append(evt)
                yield _sse(evt)
                if evt["type"] == "done":
                    run.finished = True
                    break
                getter = asyncio.ensure_future(run.events.get())
            if run.runner in completed:
                # runner 提前结束（异常兜底），避免客户端永久等待
                if not run.events.empty():
                    continue
                exc = run.runner.exception()
                if exc is not None:
                    err = ErrorEvent(message=f"编排异常: {exc}").emit()
                    err["seq"] = run.next_seq
                    run.next_seq += 1
                    run.buffer.append(err)
                    yield _sse(err)
                done_evt = DoneEvent().emit()
                done_evt["seq"] = run.next_seq
                run.next_seq += 1
                run.buffer.append(done_evt)
                yield _sse(done_evt)
                run.finished = True
                break
    finally:
        getter.cancel()
        if run.finished:
            await _retire_run(run)
        else:
            # 客户端断开且回合未完 → 进宽限（重连可续播；到期看门狗收尾）。
            # Client gone and the turn unfinished → grace (a reconnect resumes; the
            # watchdog wraps up on expiry).
            run.connected = False
            _arm_grace(run)


@router.post("/voice/resume", response_model=ApiResponse)
async def voice_resume(request: Request):
    """断线重连：回放 seq > last_seq 的已消费事件并挂接实况流（docs/designs/06）。

    - 无运行句柄 / 已完成 → 404 `no_run`（前端走历史重载兜底）；
    - 宽限期内取消看门狗、标记已连接，之后与首连同一生成器续编号。

    Reconnect: replay consumed events with seq > last_seq and attach to the live
    stream (docs/designs/06). No run handle / already finished → 404 `no_run` (the
    frontend falls back to reloading history). Inside the grace window the watchdog
    is cancelled and the run marked connected; numbering then continues through the
    same generator the first connection used.
    """
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    session_id = str(params.get("session_id") or "")
    try:
        last_seq = int(params.get("last_seq") or 0)
    except (TypeError, ValueError):
        last_seq = 0
    run = state.get_run(session_id)
    if run is None or run.finished:
        return JSONResponse({"ok": False, "error": "no_run"}, status_code=404)
    if run.grace_task is not None and not run.grace_task.done():
        run.grace_task.cancel()
    run.connected = True
    return StreamingResponse(_replay_then_live(run, last_seq), media_type="text/event-stream")


async def _replay_then_live(run: state.RunHandle, last_seq: int):
    """缺口回放 + 挂接实况（/voice/resume 的流体；抽成模块级便于直接驱动测试）。

    Replay the gap then attach to the live stream (the body of /voice/resume,
    extracted to module level so tests can drive it directly).

    Args:
        run: 运行句柄。The run handle.
        last_seq: 客户端已收到的最大 seq。The largest seq the client received.

    Yields:
        SSE 帧。SSE frames.
    """
    # 缺口回放：首连已消费进 buffer 的事件（带定型 seq），只发游标之后的。
    # Gap replay: events the first connection consumed into the buffer (seq fixed);
    # only those past the cursor are sent.
    for evt in list(run.buffer):
        if int(evt.get("seq") or 0) > last_seq:
            yield _sse(evt)
    # 挂接实况：断线期间积压在队列的事件由本连接续消费、续编号。
    # Attach live: events backloged in the queue during the outage are consumed
    # and numbered by this connection.
    async for chunk in _stream_run(run):
        yield chunk


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
    # qid 可选：携带且与当前待答问题不符 → 409（防陈旧语音作答错配到新问题）；
    # 缺省不带则照旧投递（兼容旧前端）。
    # qid is optional: when present and mismatched with the pending question the
    # delivery is refused with 409 (a stale voice answer cannot be mismatched onto
    # a newer question); absent means legacy behavior (compatible with old frontends).
    raw_qid = params.get("qid")
    qid = raw_qid.strip() if isinstance(raw_qid, str) and raw_qid.strip() else None
    raw_source = params.get("source")
    source = raw_source.strip() if isinstance(raw_source, str) and raw_source.strip() else None
    if not channel.answer(str(params.get("text") or ""), choice, qid=qid, source=source):
        return JSONResponse({"ok": False, "error": "问题已过期或 qid 不匹配"}, status_code=409)
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
