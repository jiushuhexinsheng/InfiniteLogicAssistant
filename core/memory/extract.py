# -*- coding: utf-8 -*-
"""任务后事实提取 — LLM 结构化输出 facts → FactStore（失败静默，不阻塞主流程）。Post-task fact extraction — LLM structured-output facts → FactStore (failures are silent and never block the main flow)."""
import json

from core import config
from core.llm.client import get_llm_client
from core.logger import logger
from core.memory.facts import FactStore
from core.orchestrator.task import Task
from core.prompts import EXTRACT_FACTS_SYSTEM

_FACTS_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_facts",
        "description": "从任务执行中提取值得长期记住的事实",
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "content": {"type": "string"},
                            # 分层路径（docs/designs/04 §3.3）：按语义归类，空=未分类。
                            # Hierarchy path (docs/designs/04 §3.3): semantic class; empty = unclassified.
                            "path": {"type": "string", "enum": ["偏好", "习惯", "项目", "环境", "其他"]},
                        },
                        "required": ["topic", "content"],
                    },
                },
            },
            "required": ["facts"],
        },
    },
}


def _recent_dialog(messages: list[dict], n: int) -> str:
    """取最近 n 条用户/助手对话（各截 200 字）——给 LLM 解「他/那里」类指代
    （docs/designs/04 §3.3：旧版只喂任务与结果，指代无从解析是提取失真的一大来源）。

    Take the last n user/assistant exchanges (each truncated to 200 chars) so the LLM
    can resolve "he/there"-style references (docs/designs/04 §3.3: the old prompt fed
    only the task and result, and unresolved references were a major source of
    extraction errors).

    Args:
        messages: 会话消息列表。Session message list.
        n: 取几条（用户/助手各 n）。How many of each role to take.

    Returns:
        格式化对话文本（无则空串）。Formatted dialog text (empty when none).
    """
    picked = [m for m in messages if m.get("role") in ("user", "assistant")
              and isinstance(m.get("content"), str) and m["content"].strip()]
    if not picked or n <= 0:
        return ""
    tail = picked[-(n * 2):]
    lines = [f"- {'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}" for m in tail]
    return "最近对话：\n" + "\n".join(lines) + "\n"


async def extract_and_store(task: Task, result: dict, store: FactStore,
                            session=None) -> None:
    """任务结束后提取用户事实写入记忆；非 done/failed 或 LLM 失败时静默跳过。

    session 非空时：① 提取输入附最近对话（指代可解）；② 写入带 path（LLM 归类）与
    origin（溯源坐标，docs/designs/04 §3.3/§3.5）。

    Extract user facts after a task finishes and persist them to memory; silently
    skip when the task is not done/failed or the LLM call fails. With a session:
    ① the prompt gains the recent dialog (references resolve); ② writes carry path
    (LLM-assigned class) and origin (provenance, docs/designs/04 §3.3/§3.5).

    Args:
        task: 已完成的任务。The finished task.
        result: 任务执行结果 dict（含 status / summary / steps）。The task result dict (with status / summary / steps).
        store: 事实存储。The fact store.
        session: 可选会话（提供前文与溯源）。Optional session (recent dialog + provenance).
    """
    if not result or result.get("status") not in ("done", "failed"):
        return
    msgs = list(getattr(session, "messages", None) or [])
    recent = ""
    origin = None
    if session is not None:
        # 注意：不要在函数内再 `from core import config` —— 顶层已导入，函数内同名导入会把
        # 整个函数作用域的 config 变成局部变量，session=None 分支下后续读取直接 UnboundLocal。
        # Do not re-import config inside the function: the module already imports it, and a
        # function-level import shadows it as a local, breaking later reads on the
        # session=None path.
        try:
            n = config.settings.memory.extract_recent_messages
        except Exception:
            n = 2
        recent = _recent_dialog(msgs, n)
        last = msgs[-1] if msgs else {}
        origin = {"conv_id": getattr(session, "id", ""),
                  "turn_id": last.get("turn_id", "")}
    user_content = (
        f"任务：{task.goal}\n"
        f"{recent}"
        f"结果：{result.get('summary', '')}\n"
        f"步骤：{json.dumps((result.get('steps') or [])[:5], ensure_ascii=False)}"
    )
    messages = [
        {"role": "system", "content": EXTRACT_FACTS_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    try:
        async for evt in get_llm_client().retry_stream_chat(
            messages, tools=[_FACTS_TOOL], temperature=config.settings.agent.structured_temperature,
        ):
            if evt["type"] == "done":
                msg = evt["message"]
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                for f in data.get("facts") or []:
                    topic = str(f.get("topic") or "").strip()
                    content = str(f.get("content") or "").strip()
                    if topic and content:
                        await store.upsert(topic, content, source=f"task:{task.id}",
                                           path=str(f.get("path") or ""), origin=origin)
                return
    except Exception as e:
        logger.warning("extract_and_store 失败: {}", e)
