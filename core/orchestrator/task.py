# -*- coding: utf-8 -*-
"""任务（本轮目标）— 目标 / 参数 / 风险 / 复杂度

"任务"不再是用户可见的模式：每一轮输入都形成一个轻量的本轮目标交给执行循环，
由模型自己决定要不要调工具。任务级确认与澄清循环已删除；风险仍只用于工具级确认
（真正的执行闸门在 confirm_tool）。

Task (one turn's goal) — goal / params / risk / complexity. A "task" is no longer a
user-visible mode: every turn forms a lightweight goal for the execution loop and the
model decides whether to call tools. The task-level confirmation and clarification
loops are gone; risk now only feeds tool-level confirmation (the real execution gate
is confirm_tool).
"""
from dataclasses import dataclass, field


@dataclass
class Task:
    """本轮目标：目标、参数、风险、复杂度与执行状态。

    One turn's goal: goal, params, risk, complexity and execution state.
    """

    id: str
    goal: str
    params: dict = field(default_factory=dict)
    risk: str = "read"
    state: str = "queued"  # queued/planning/running/waiting_question/waiting_confirm/done/failed/stopped
    # 创建时间（ISO 字符串）：审计与落盘用。直接构造的 Task 缺省为空串。
    # Creation timestamp (ISO string) for auditing/persistence; empty when constructed directly.
    created: str = ""
    # 意图判断给出的复杂度：只有 complex 才可能交给多智能体。
    # Complexity from intent judging: only "complex" may go to the multi-agent path.
    complexity: str = "simple"
