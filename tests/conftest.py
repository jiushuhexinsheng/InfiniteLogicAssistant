# -*- coding: utf-8 -*-
"""跨文件共享的测试夹具。Shared test fixtures.
"""
import pytest


@pytest.fixture
def asking_policy(monkeypatch):
    """把工具/任务权限判定钉成「询问」。

    2026-09-13 起仓库默认**三档全放行**（用户要求），于是「高风险工具要先确认」这条路径
    不再自然触发。而多个测试文件要验证的正是这类安全属性 —— 「未经确认不得执行」
    「拒绝确认则不执行」—— 不钉住策略的话，这些用例会因为默认放行而形同虚设
    （更糟：可能因为「没执行」的断言恰好成立而**假通过**）。

    钉住的是**每个消费方模块自己那份** `decide` 引用：各模块用的是
    `from core.tools.policy import decide`，拿到的是绑定到自己命名空间的副本，因此只改
    `core.tools.policy.decide` 或只改 `confirm` 都不够 —— 必须逐模块替换。新增消费方时
    记得同步加进来。

    Pins the tool/task permission decision to "ask". Since 2026-09-13 the repository default is
    **allow on every tier** (at the user's request), so the "high-risk tools need confirmation"
    path no longer triggers on its own. Several test files verify exactly that class of safety
    property — "not executed without confirmation", "a refusal means no execution" — and without
    pinning they would be hollow, or worse, **pass for the wrong reason** (an assertion about
    something not happening holds trivially when nothing is ever asked).

    It patches **each consumer module's own** `decide` reference: modules do
    `from core.tools.policy import decide`, which binds a copy into their namespace, so patching
    `core.tools.policy.decide` alone — or `confirm` alone — is not enough. Add new consumers here.
    """
    from core.agent import base as agent_base
    from core.api import tools as api_tools
    from core.orchestrator import confirm as confirm_mod
    from core.orchestrator import executor as orch_executor
    from core.tools.policy import Decision

    ask = lambda name, section=None: Decision("ask", "test")   # noqa: E731
    ask_tier = lambda risk, section=None: Decision("ask", "test")   # noqa: E731

    for mod in (confirm_mod, agent_base, api_tools, orch_executor):
        monkeypatch.setattr(mod, "decide", ask)
    monkeypatch.setattr(confirm_mod, "decide_tier", ask_tier)
