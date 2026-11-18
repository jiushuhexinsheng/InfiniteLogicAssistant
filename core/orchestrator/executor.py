# -*- coding: utf-8 -*-
"""执行循环 — plan → act(调工具) → observe(回喂) → reflect，可取消、可收敛

高风险工具（risk != read）在调用前经 confirm_if_needed 确认。
取消（CancelledError）统一收敛为 status=stopped 返回，调用方无需捕获。

单个 ReAct 回合被拆成可单测的私有步骤：
`_load_context`（RAG/记忆）→ `_seed_history`（system 提示 + 首条用户消息）→
`_condense`（滚动压缩）→ `_stream_turn`（一轮流式）→ `_run_tool_calls`（免确认并发、
需确认串行）→ `_apply_tool_results`（steps/history/块落库）。
`execute_task` 只负责串联这些步骤与收尾，不再内联 286 行。

Execution loop — plan → act (call tools) → observe (feed back) → reflect; cancellable
and convergent. High-risk tools are confirmed before being called. Cancellation is
converged into status=stopped so callers need not catch it.

One ReAct turn is decomposed into unit-testable private steps: context loading
(RAG/memory) → history seeding (system prompt + first user message) → rolling
condense → one streamed turn → tool dispatch (prompt-free concurrently, confirmation-
bound serially) → result persistence (steps/history/blocks). execute_task only wires
them together and wraps up.
"""
import asyncio
import json
from dataclasses import dataclass

from core.agent.coordinator import run_coordinator
from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.memory.context import build_context_with_sources
from core.orchestrator.blocks import HISTORY_LEN, PREVIEW_LEN, llm_tool_feed, make_block
from core.orchestrator.condense import maybe_condense
from core.orchestrator.confirm import confirm_tool
from core.orchestrator.control import CancellationToken, PauseController
from core.orchestrator.events import BlockEvent, ContentDeltaEvent, ToolEndEvent, ToolStartEvent, from_llm_event
from core.orchestrator.session import Session
from core.orchestrator.task import Task
from core.orchestrator.voice_reply import VoiceReplySplitter, split_voice_reply
from core.tools import TOOLS
from core.tools.policy import decide

from core.prompts import DESCRIBE_NOTE, EXECUTOR_SYSTEM as _SYSTEM, RAG_CITE_NOTE, UNTRUSTED_DATA_NOTE


def should_use_multi_agent(task: Task) -> bool:
    """只有意图判断为 complex 且启用多智能体时才转协调者。

    判据不再是「参数多/目标长」—— 那只是文本形状，与真复杂度无关；复杂度由
    judge_intent 给出，执行层只按它路由。

    Route to the coordinator only when intent judging says "complex" and multi-agent
    is enabled. The old heuristics (many params / long goal) measured text shape, not
    real complexity; complexity now comes from judge_intent and execution just routes
    on it.
    """
    return config.settings.agent.multi_agent and task.complexity == "complex"


def _stopped(steps: list[dict]) -> dict:
    """构造 stopped 结果（统一收尾文案，避免四处手写同一 dict）。

    Build the stopped result (unified wrap-up text instead of four hand-written dicts).
    """
    return {"status": "stopped", "summary": "已停止", "steps": steps}


async def _run_multi_agent(task: Task, session: Session, cancel: CancellationToken,
                           events: asyncio.Queue | None,
                           pause: PauseController | None) -> dict:
    """复杂任务转多智能体协调者，把子任务与完整报告整理成 steps。

    Delegate a complex task to the multi-agent coordinator and turn its subtasks plus
    the full report into steps.
    """
    cr = await run_coordinator(task, session, cancel, events, pause=pause)
    steps = [
        {"step": i, "tool": f"agent:{x['agent_type']}", "status": x["status"],
         # 产物路径附在结果尾部（docs/designs/08 批3）：汇总卡可见完整输出去向。
         # Artifact path appended (docs/designs/08 batch 3): the summary card shows
         # where the full output lives.
         "result": x["output"] + (f"\n[产物] {x['artifact']}" if x.get("artifact") else "")}
        for i, x in enumerate(cr["subtasks"])
    ]
    # done.summary 只放语音摘要（≤60 字）；完整报告作为最后一步进 steps（docs/designs/10 5.5）。
    # done.summary carries only the short voice line; the full report goes into
    # steps as a final entry (docs/designs/10 5.5).
    report = cr.get("report") or cr["summary"]
    steps.append({"step": len(steps), "tool": "agent:report",
                  "status": cr["status"], "result": report})
    summary = cr["summary"]
    # 把最终摘要按 content_delta 流式返回（前端累积 → 语音播报真实结论）
    if events is not None and summary:
        for i in range(0, len(summary), 200):
            await events.put(ContentDeltaEvent(text=summary[i:i + 200]).emit())
    session.append("assistant", report)
    return {"status": cr["status"], "summary": summary, "steps": steps}


async def _load_context(task: Task) -> tuple[str, list[dict]]:
    """取 RAG + 长期记忆上下文与引用来源；失败返回空（不影响执行）。

    Load the RAG + long-term-memory context and its sources; any failure yields empty
    values and never blocks execution.
    """
    try:
        return await build_context_with_sources(
            task.goal + " " + json.dumps(task.params, ensure_ascii=False))
    except Exception:
        return "", []


async def _emit_sources(events: asyncio.Queue | None, sources: list[dict]) -> None:
    """RAG 命中 → sources 块直通前端（可折叠来源 chips；不进 text 投影）。

    RAG hits → a sources block straight to the front-end (collapsible source chips;
    excluded from the text projection).
    """
    if not sources or events is None:
        return
    await events.put(BlockEvent(block=make_block("sources", {
        "items": [
            {"n": i + 1, "path": h.get("path", ""),
             "section": h.get("section", ""), "score": h.get("score")}
            for i, h in enumerate(sources)
        ],
    })).emit())


def _seed_history(task: Task, session: Session, context: str,
                  sources: list[dict]) -> list[dict]:
    """拼出本轮起始 history：system 提示（含引用/渐进式说明）+ 首条用户消息。

    对话历史取最近 10 条并去掉当前轮用户消息（它会被重新作为首条消息）。
    纯函数（只读 session），可脱离 LLM 单测。

    Build the turn's initial history: system prompt (with citation/progressive notes)
    plus the first user message. The last 10 session messages are included minus the
    current user message (re-added as the first message). Pure (session read-only), so
    it is testable without an LLM.
    """
    prior = [m for m in session.summary(10) if m.get("role") in ("user", "assistant")][:-1]
    context_lines = []
    if context:
        context_lines.append(f"以下是与任务相关的已知信息：\n{context}")
    if prior:
        lines = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
            for m in prior if isinstance(m.get("content"), str)
        )
        context_lines.append(f"以下是最近对话：\n{lines}")
    base = f"{_SYSTEM}\n\n{UNTRUSTED_DATA_NOTE}"
    if sources:
        base += f"\n\n{RAG_CITE_NOTE}"  # 有编号命中才要求标注（docs/designs/05 §3.1）。
    if config.settings.tools.lazy_groups:
        # 渐进式加载开启才附说明（默认关 = prompt 零变化，docs/designs/08 批4）。
        # Only when progressive loading is on (off by default = zero prompt change).
        base += f"\n\n{DESCRIBE_NOTE}"
    sys_prompt = f"{base}\n\n" + "\n\n".join(context_lines) if context_lines else base
    return [
        {"role": "system", "content": sys_prompt},
        # 用户原话直接作为首条消息（不再套「任务目标」外壳 —— 闲聊与任务同一条管线，
        # 套壳会让模型把「你好」当成任务名）。
        # The raw utterance is the first message (no "task goal" wrapper — chat and
        # tasks share one pipeline, and the wrapper made the model treat "你好" as a
        # task title).
        {"role": "user", "content": task.goal + (
            f"\n参考参数：{json.dumps(task.params, ensure_ascii=False)}" if task.params else "")},
    ]


async def _condense(history: list[dict], session: Session) -> list[dict]:
    """滚动压缩（docs/designs/08 批2）：只动本轮 LLM 视角，超阈值折叠中间段。

    压缩对用户可见（notify），会话持久化不受影响；任何异常都返回原 history
    （fail-open 不丢任务）。

    Rolling condenser (docs/designs/08 batch 2): LLM view only — fold the middle once
    over the threshold; visible to the user (notify), persisted session untouched.
    Any failure returns the original history (fail-open, never drops the task).
    """
    try:
        history, omitted = await maybe_condense(
            history,
            threshold_chars=config.settings.agent.condense_threshold_chars,
        )
        if omitted:
            await session.notify(f"上下文已压缩（省略 {omitted} 条中间消息）")
    except Exception:
        pass
    return history


@dataclass
class _Turn:
    """一轮 LLM 流式的产物（供 execute_task 判定暂停/停止/正常收尾）。

    The outcome of one streamed LLM turn (lets execute_task distinguish paused /
    stopped / normal completion).
    """

    message: dict | None = None   # 归一化后的 assistant 消息。Normalized assistant message.
    speech: str = ""              # 语音摘要（done.summary）。Spoken summary (done.summary).
    visible: str = ""             # 展示正文（不含语音段）。Visible body (speech excluded).
    partial: str = ""             # 暂停中断时的已生成部分。Partial output on pause abort.
    paused: bool = False          # 是否因暂停中断。Whether a pause aborted the stream.
    stopped: bool = False         # 是否因停止中断。Whether cancellation aborted the stream.


async def _stream_turn(history: list[dict], cancel: CancellationToken,
                       pause: PauseController | None,
                       events: asyncio.Queue | None) -> _Turn:
    """跑一轮 LLM 流式：转发增量、拆分语音/正文、处理暂停与停止。

    停止 → `_Turn(stopped=True)`；暂停中断 → `_Turn(paused=True, partial=...)`；
    正常结束 → 归一化后的 assistant 消息（无流式增量时回落到最终消息解析）。

    Run one streamed LLM turn: forward deltas, split speech from body, and handle
    pause/stop. Stop → stopped turn; pause abort → paused turn with the partial body;
    normal completion → normalized assistant message (falling back to parsing the
    final message when no delta was streamed).
    """
    assistant_message = None
    splitter = VoiceReplySplitter()
    pause_aborted = False
    async for evt in get_llm_client().retry_stream_chat(
            history, tools=TOOLS.schemas(stub_groups=config.settings.tools.lazy_groups)):
        if pause is not None and pause.abort_llm:
            pause_aborted = True
            break
        if cancel.is_cancelled:
            # 停止按钮：流在跑也要立刻收手（不能等到步骤边界）。
            # Stop button: quit the running stream at once (not only at step
            # boundaries).
            return _Turn(stopped=True)
        if evt["type"] == "done":
            assistant_message = evt["message"]
        elif evt["type"] == "content_delta":
            visible = splitter.feed(str(evt.get("text") or ""))
            if visible and events is not None:
                await events.put(ContentDeltaEvent(text=visible).emit())
        elif events is not None:
            # reasoning_delta / usage 等经统一口径转发；正文由 splitter 接管
            # （语音段不进入聊天流）。
            # Forward reasoning/usage through the shared adapter; body content is
            # owned by the splitter (the speech segment never reaches chat).
            forwarded = from_llm_event(evt)
            if forwarded is not None:
                await events.put(forwarded)
    if pause_aborted:
        # 快照而非 finish：暂停中断只取已生成部分，不破坏解析器状态。
        # Snapshot (not finish): a pause abort only reads what was produced.
        _, partial = splitter.snapshot()
        return _Turn(paused=True, partial=partial)
    if assistant_message is None:
        return _Turn()
    speech, visible_content = splitter.finish()
    if not visible_content:
        # 无流式增量（测试桩/非流式路径）：直接解析最终消息。
        speech, visible_content = split_voice_reply(
            str(assistant_message.get("content") or ""))
    return _Turn(
        message={**assistant_message, "content": visible_content},
        speech=speech,
        visible=visible_content,
    )


async def _run_one_tool(tc: dict, step: int, session: Session, cancel: CancellationToken,
                        pause: PauseController | None,
                        events: asyncio.Queue | None) -> tuple[dict, dict, str] | None:
    """执行单个工具调用，返回 (steps条目, tool消息[原文], LLM口径正文)；取消返回 None。

    高风险工具先确认；拒绝时把理由（截断防注入）与纠偏指引回喂 LLM。暂停中若
    收到 force 中断，取消在途工具并记录为 error。

    Execute one tool call, returning (steps entry, tool message [raw], LLM-side body);
    return None when cancelled. High-risk tools are confirmed first; a refusal feeds
    the rationale (truncated against injection) plus corrective guidance back to the
    LLM. A force pause cancels the in-flight tool and records it as an error.
    """
    cancel.throw_if_cancelled()
    name = tc["function"]["name"]
    call_id = tc.get("id", "")
    raw = tc["function"].get("arguments") or "{}"
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        args = {}
    if events is not None:
        await events.put(ToolStartEvent(name=name, args=args, call_id=call_id).emit())
    # 高风险工具先确认（基于工具实际风险，而非任务声明的 risk）
    conf = await confirm_tool(session, name, args)
    if conf:
        if pause is not None:
            await pause.wait_if_paused()
            tool_task = asyncio.ensure_future(
                TOOLS.acall(name, args, cancel=cancel, session=session))
            force_task = asyncio.ensure_future(pause.wait_force())
            done, _ = await asyncio.wait(
                {tool_task, force_task}, return_when=asyncio.FIRST_COMPLETED)
            if force_task in done and not tool_task.done():
                tool_task.cancel()
                await asyncio.gather(tool_task, return_exceptions=True)
                pause.record_interrupted(name, args, TOOLS.risk(name))
                result = f"Error: 工具 {name} 被暂停中断（恢复后可重跑或跳过）"
            else:
                force_task.cancel()
                result = await tool_task
        else:
            result = await TOOLS.acall(name, args, cancel=cancel, session=session)
    else:
        # 拒绝理由回喂 LLM 作为纠偏信号（截断防注入）；无理由时文案
        # 仅在尾部多一段指引，模型不会把同一调用原样重试。
        # The refusal rationale is fed back to the LLM as a corrective
        # signal (truncated against injection); without a rationale the
        # message only gains a guidance tail, so the model does not
        # blindly retry the same call.
        result = f"Error: 操作者拒绝调用 {name}"
        if conf.reason:
            result += f"（理由：{conf.reason[:200]}）"
        result += "。请调整方案、换用其他工具，或先向用户说明后再请求。"
    status = "error" if result.startswith("Error") else "ok"
    if events is not None:
        await events.put(ToolEndEvent(
            name=name, status=status, output=result[:PREVIEW_LEN],
            call_id=call_id, truncated=len(result) > PREVIEW_LEN,
            output_len=len(result),
        ).emit())
    return (
        {"step": step, "tool": name, "args": args, "status": status, "result": result[:PREVIEW_LEN]},
        {"role": "tool", "tool_call_id": call_id, "content": result},
        llm_tool_feed(result),   # LLM 口径（docs/designs/08 批1）。LLM-side convention.
    )


async def _run_tool_calls(tool_calls: list[dict], step: int, session: Session,
                          cancel: CancellationToken, pause: PauseController | None,
                          events: asyncio.Queue | None) -> dict[int, tuple[dict, dict, str]]:
    """按「是否需要确认」分流：免确认的并发、需确认的串行（确认本身必须串行问）。

    返回 {原始下标: (steps条目, tool消息, LLM口径正文)}；取消返回 None 的调用被丢弃。

    Split by "needs confirmation": prompt-free calls run concurrently, confirmation-
    bound ones serially (the confirmation itself must be asked serially). Returns
    {original index: (steps entry, tool message, LLM-side body)}; cancelled calls
    (None) are dropped.
    """
    # 分流依据是「是否需要确认」而非工具风险 —— 策略 allow 的写操作同样免确认。
    # The split is by "needs confirmation", not by tool risk: a policy-allowed write
    # is equally prompt-free.
    auto_idx = [i for i, tc in enumerate(tool_calls)
                if decide(tc["function"]["name"]).action == "allow"]
    auto_set = set(auto_idx)
    ask_idx = [i for i in range(len(tool_calls)) if i not in auto_set]
    results: dict[int, tuple[dict, dict, str]] = {}
    if auto_idx:
        outs = await asyncio.gather(*(_run_one_tool(tool_calls[i], step, session, cancel, pause, events)
                                      for i in auto_idx))
        for i, o in zip(auto_idx, outs):
            if o is not None:
                results[i] = o
    for i in ask_idx:
        o = await _run_one_tool(tool_calls[i], step, session, cancel, pause, events)
        if o is not None:
            results[i] = o
    return results


def _apply_tool_results(results: dict[int, tuple[dict, dict, str]], steps: list[dict],
                        history: list[dict], session: Session) -> None:
    """按原 tool_calls 顺序落 steps/history/会话块，保持回喂顺序稳定。

    history 的 tool 正文用 LLM 口径（截断），steps/块用原文（docs/designs/08 批1）；
    工具以 tool 块入会话（不产生独立 "tool" 消息行）。

    Land steps/history/session blocks in the original tool_calls order so feedback
    stays stable. The history tool body uses the LLM-side (truncated) convention while
    steps/blocks keep the raw text; tools enter the session as tool blocks (no
    standalone "tool" message rows).
    """
    for i in sorted(results):
        step_entry, tool_msg, feed = results[i]
        steps.append(step_entry)
        history.append({**tool_msg, "content": feed})
        # output 入库截 HISTORY_LEN、预览/完整长度随块记录；content 投影里的
        # "name: output[:200]" 文本行承担旧读路径兼容。
        # Output is stored up to HISTORY_LEN with preview/full lengths recorded; the
        # "name: output[:200]" line in the content projection serves legacy read paths.
        full_out = tool_msg["content"]
        session.append_block("assistant", make_block("tool", {
            "call_id": tool_msg.get("tool_call_id", ""),
            "name": step_entry["tool"],
            "args": step_entry.get("args", {}),
            "status": step_entry["status"],
            "output": full_out[:HISTORY_LEN],
            "output_preview": full_out[:PREVIEW_LEN],
            "truncated": len(full_out) > PREVIEW_LEN,
            "full_len": len(full_out),
        }))


async def execute_task(task: Task, session: Session, cancel: CancellationToken,
                       events: asyncio.Queue | None = None,
                       pause: PauseController | None = None) -> dict:
    """执行任务：复杂任务转多智能体协调者；简单任务走 ReAct。

    events 非空时流式发射 tool_start/tool_end/usage/content_delta（SSE 实时呈现）。
    返回 {status: done|failed|stopped, summary, steps:[...]}。

    Execute the task: complex tasks go to the multi-agent coordinator; simple
    tasks run a ReAct loop. When events is not None,
    tool_start/tool_end/usage/content_delta are streamed (real-time SSE
    rendering). Returns {status: done|failed|stopped, summary, steps:[...]}.
    """
    if cancel.is_cancelled:
        return _stopped([])

    # 复杂任务 → 多智能体
    if should_use_multi_agent(task):
        return await _run_multi_agent(task, session, cancel, events, pause)

    max_steps = config.settings.agent.recursion_limit
    context, sources = await _load_context(task)
    await _emit_sources(events, sources)
    history = _seed_history(task, session, context, sources)
    steps: list[dict] = []
    for step in range(max_steps):
        if pause is not None:
            await pause.wait_if_paused()
        if cancel.is_cancelled:
            return _stopped(steps)
        history = await _condense(history, session)
        try:
            if pause is not None:
                await pause.wait_if_paused()
            cancel.throw_if_cancelled()
            turn = await _stream_turn(history, cancel, pause, events)
            if turn.stopped:
                return _stopped(steps)
            if turn.paused:
                if turn.partial:
                    history.append({"role": "assistant", "content": turn.partial})
                if pause is not None:
                    await pause.wait_if_paused()
                history.append({"role": "system", "content":
                                "上一段回答因操作者暂停而中断。请从中断处继续，不要重复已输出的内容。"})
                continue
            if turn.message is None:
                return {"status": "failed", "summary": "LLM 返回空消息", "steps": steps}

            history.append(turn.message)
            if pause is not None:
                await pause.wait_if_paused()
            tool_calls = turn.message.get("tool_calls") or []
            if not tool_calls:
                content = turn.visible or "完成"
                session.append("assistant", content)
                # done.summary 只承载语音总结；完整正文已作为 content 流/消息落库。
                # done.summary carries the spoken summary only; the full body is already
                # streamed and persisted as content.
                return {"status": "done", "summary": turn.speech or "完成", "steps": steps}

            results = await _run_tool_calls(tool_calls, step, session, cancel, pause, events)
            _apply_tool_results(results, steps, history, session)
        except asyncio.CancelledError:
            return _stopped(steps)
        except Exception as e:
            logger.error("executor 执行异常: {}", e)
            return {"status": "failed", "summary": f"执行失败: {e}", "steps": steps}
    return {"status": "failed", "summary": f"超出执行步数上限（{max_steps}）", "steps": steps}
