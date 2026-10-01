# -*- coding: utf-8 -*-
"""编排 SSE 端点:utter 入口 / 断线恢复 / 作答投递 / 任务停止 + 运行流辅助。

Orchestration SSE endpoints: utter entry / disconnect resume / answer delivery /
task stop, plus the run-stream helpers (shared by first connect and resume).
"""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from core import config as config
from core.api import state
from core.api.schemas import AckResponse, ApiResponse
from core.logger import logger
from core.orchestrator.events import DoneEvent, ErrorEvent

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
