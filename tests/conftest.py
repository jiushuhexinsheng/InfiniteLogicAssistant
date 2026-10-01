# -*- coding: utf-8 -*-
"""跨文件共享的测试夹具。Shared test fixtures.

确认语义不依赖开发者本地 config.yaml（例如本地开了 auto_approve），所以整个套件默认跑在
安全默认值下，除非某个用例显式设置 auto_approve=True 来验证开启行为。

Confirmation semantics must not depend on the developer's local config.yaml (e.g. a
locally-enabled auto_approve), so the whole suite runs under the safe default unless an
individual test explicitly opts in by setting auto_approve to True.
"""
import re
from importlib import metadata
from pathlib import Path

import pytest

from core import config


def _parse_pins(text: str) -> list[tuple[str, str]]:
    """从 requirements 文本提取 ``name==ver`` 钉版对。

    Extract ``(name, version)`` pins from requirements text. Lines that are blank,
    comments, or pip options (``-r``/``--find-links``/``-e``) are skipped; env
    markers (``; marker``) are stripped before matching; extras (``pkg[standard]``)
    are accepted but not returned. Unpinned lines are ignored — this parser only
    serves the drift check, which needs exact pins to compare against.
    """
    pins: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-")):
            continue
        line = line.split(";", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*==\s*([^\s;#]+)", line)
        if m:
            pins.append((m.group(1), m.group(2)))
    return pins


def _check_requirements() -> None:
    """收集前预检:requirements 里钉死的包必须已装且版本一致(环境漂移主动拦截)。

    Preflight before collection: every pinned package in requirements*.txt must be
    installed at the exact pinned version, so local environment drift fails fast
    with an actionable message instead of surfacing as a confusing import error
    (or, worse, silently different behavior) mid-suite.

    只检查发行版名(importlib.metadata),不做 import —— Pillow→PIL 这类导入名与
    发行名不一致的情况不会误报。
    """
    root = Path(__file__).resolve().parent.parent
    problems: list[str] = []
    for req_file in ("requirements.txt", "requirements-dev.txt"):
        req_path = root / req_file
        if not req_path.is_file():
            continue
        for name, want in _parse_pins(req_path.read_text(encoding="utf-8")):
            try:
                have = metadata.version(name)
            except metadata.PackageNotFoundError:
                problems.append(f"{name}=={want}  未安装 (not installed)")
                continue
            if have != want:
                problems.append(f"{name}=={want}  本地 {have} (version drift)")
    if problems:
        raise RuntimeError(
            "环境漂移 — requirements 与本机不一致 (environment drift):\n  "
            + "\n  ".join(problems)
            + "\n修复 (fix): pip install --find-links=scripts/libs "
            "-r requirements.txt -r requirements-dev.txt"
        )


_check_requirements()


@pytest.fixture(autouse=True)
def _auto_approve_off(monkeypatch):
    """每个测试前把 agent.auto_approve 钉为 False；需要验证开启行为的用例可自行置 True。

    Pins agent.auto_approve to False before every test; tests that verify the
    enabled behavior may set it to True themselves.
    """
    monkeypatch.setattr(config.settings.agent, "auto_approve", False)


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
