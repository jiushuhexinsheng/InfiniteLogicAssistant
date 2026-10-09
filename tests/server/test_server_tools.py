# -*- coding: utf-8 -*-
"""单工具执行 /api/tools/call 及其权限策略分支。
Single tool execution via /api/tools/call and its permission-policy branches.
"""


# ─── 单工具执行 ───

def test_tools_call_ok(client):
    """测试单工具调用成功返回输出。Tests a successful single tool call returning output."""
    resp = client.post("/api/tools/call", json={"name": "get_datetime", "args": {}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "ok"
    assert data["output"]


def test_tools_call_calculate(client):
    """测试 calculate 工具计算表达式。Tests the calculate tool evaluating an expression."""
    resp = client.post("/api/tools/call", json={"name": "calculate", "args": {"expression": "2+3*4"}})
    assert resp.status_code == 200
    assert resp.json()["output"] == "14"


def test_tools_call_unknown_404(client):
    """测试调用未知工具返回 404。Tests calling an unknown tool returning 404."""
    resp = client.post("/api/tools/call", json={"name": "no_such_tool", "args": {}})
    assert resp.status_code == 404
    assert resp.json()["ok"] is False


def test_tools_call_invalid_args(client):
    """测试非法参数返回 400。Tests invalid arguments returning 400."""
    resp = client.post("/api/tools/call", json={"name": "get_datetime", "args": "not-a-dict"})
    assert resp.status_code == 400


def test_tools_call_bad_json(client):
    """测试请求体非 JSON 时返回 400。Tests a non-JSON request body returning 400."""
    resp = client.post("/api/tools/call", content="not json")
    assert resp.status_code == 400


def test_tools_call_high_risk_requires_confirm(client, asking_policy):
    """测试高风险工具未带 confirm 时要求确认。Tests high-risk tools requiring confirmation without a confirm flag.

    必须钉住策略为 ask：默认已改为全放行，不钉的话这个请求会直接执行，
    用例断言的「需要确认」就测不到了。
    The policy must be pinned to ask: the default is now allow-everything, so without pinning the
    request would simply execute and the asserted "needs confirmation" would go untested.
    """
    # 非 read 工具无 confirm 字段 → 返回 needs_confirm，不执行
    resp = client.post("/api/tools/call", json={"name": "write_file", "args": {"path": "C:/x.txt", "content": "hi"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["needs_confirm"] is True


def test_tools_call_high_risk_with_confirm_executes(client, monkeypatch, asking_policy):
    """测试高风险工具带 confirm 后执行。Tests high-risk tools executing when confirm is provided.

    同样钉住 ask —— 否则「带不带 confirm 都能跑」，用例不再能证明 confirm 起了作用。
    Also pinned to ask; otherwise it would pass with or without the confirm flag and no longer
    demonstrate that the flag is what let it through.
    """
    async def fake_acall(name, args):
        return "ok-stubbed"
    monkeypatch.setattr("core.api.tools.TOOLS.acall", fake_acall)
    resp = client.post("/api/tools/call", json={
        "name": "write_file", "args": {"path": "x", "content": "y"}, "confirm": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["output"] == "ok-stubbed"


# ─── /api/tools/call 走权限策略 ───


def _policy_returning(action, source="rule:test"):
    from core.tools.policy import Decision
    return lambda name, section=None: Decision(action, source)


def test_tool_call_denied_by_policy_returns_403(client, monkeypatch):
    """策略 deny 的工具即使带 confirm: true 也拒绝 —— confirm 不能覆盖 deny（关键安全不变式）。
    A policy-denied tool is refused even with confirm: true — confirm cannot override
    deny (the key security invariant)."""
    from core.api import tools as tools_api
    monkeypatch.setattr(tools_api, "decide", _policy_returning("deny", "rule:run_*"))
    r = client.post("/api/tools/call",
                    json={"name": "run_shell_tool", "args": {"command": "echo hi"}, "confirm": True})
    assert r.status_code == 403
    assert "禁止" in r.json()["error"]


def test_tool_call_allowed_by_policy_needs_no_confirm(client, monkeypatch):
    """策略 allow 的工具无需 confirm 标记即可执行。A policy-allowed tool runs without the confirm flag."""
    from core.api import tools as tools_api
    monkeypatch.setattr(tools_api, "decide", _policy_returning("allow", "tier:read"))
    r = client.post("/api/tools/call", json={"name": "get_datetime", "args": {}})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_tool_call_ask_without_confirm_returns_needs_confirm(client, monkeypatch):
    """策略 ask 且未带 confirm → 返回 needs_confirm 让前端弹窗。
    A policy-ask tool without confirm returns needs_confirm so the front end can prompt."""
    from core.api import tools as tools_api
    monkeypatch.setattr(tools_api, "decide", _policy_returning("ask", "tier:exec"))
    r = client.post("/api/tools/call", json={"name": "run_shell_tool", "args": {"command": "echo hi"}})
    assert r.status_code == 200
    assert r.json().get("needs_confirm") is True


def test_tool_call_ask_with_confirm_executes(client, monkeypatch):
    """策略 ask 且带 confirm → 正常执行（前端弹窗确认后的重调路径）。
    A policy-ask tool with confirm executes normally (the front end's post-confirmation re-call)."""
    from core.api import tools as tools_api
    monkeypatch.setattr(tools_api, "decide", _policy_returning("ask", "tier:read"))
    r = client.post("/api/tools/call", json={"name": "get_datetime", "args": {}, "confirm": True})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_tool_call_denied_by_policy_is_audited(client, monkeypatch):
    """策略拒绝必须落审计 —— 被拦下的调用到不了 TOOLS.acall（那里才记日志），
    不记则拒绝事件完全静默。A policy denial must be audited: the blocked call never
    reaches TOOLS.acall (where logging happens), so otherwise it would be silent."""
    from core.api import tools as tools_api
    recorded: list[str] = []
    monkeypatch.setattr(tools_api, "audit", lambda msg: recorded.append(msg))
    monkeypatch.setattr(tools_api, "decide", _policy_returning("deny", "rule:run_*"))
    r = client.post("/api/tools/call", json={"name": "run_shell_tool", "args": {"command": "echo hi"}})
    assert r.status_code == 403
    assert len(recorded) == 1
    assert "denied" in recorded[0] and "run_shell_tool" in recorded[0] and "rule:run_*" in recorded[0]
