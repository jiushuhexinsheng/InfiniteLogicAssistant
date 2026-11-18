# -*- coding: utf-8 -*-
"""文档防漂移门禁（docs/designs/10 6.3）。

检查对象是**当前态文档**：`README.md` + `wiki/*.md`。`docs/designs/` 与
`docs/superpowers/` 是某个时点的决策记录，故意不纳入——历史文档允许提到已经删除的东西。

四类检查：
1. README / wiki 的 API 表里每个端点都必须真实存在于 OpenAPI（WS 路由另补）；
2. 已删除的路由 / 模块 / 通道标识不得再出现在当前文档；
3. 当前文档里以反引号引用的 `core/**.py` 模块必须真实存在（防「删了模块、文档还列着」）；
4. `via=` 只允许 `stream`（流式会话是唯一上传口径）。

Docs drift gate (docs/designs/10 6.3). Scope: current-state docs only (`README.md` +
`wiki/*.md`). The design/plan archives under `docs/designs/` and `docs/superpowers/`
are deliberate point-in-time records and are excluded — they may cite things that no
longer exist. Four checks: documented API paths exist in OpenAPI; deleted route/module
identifiers are gone from current docs; every `core/**.py` module cited in backticks
exists; and `via=` may only be `stream`.
"""
import re
from pathlib import Path

import server

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DOCS = [ROOT / "README.md", *sorted((ROOT / "wiki").glob("*.md"))]

# 2026-11 已删除的标识：旧编排函数与模块、旧唤醒链路、任务库前端组件、旧上传通道。
# Identifiers removed in 2026-11: legacy orchestration functions/modules, the legacy wake
# pipeline, the task-library component, and the old upload channels.
FORBIDDEN = [
    "form_task",
    "run_clarify",
    # 模块名单独禁：README 目录树只写裸模块名（`intent / task / clarify / ...`），
    # 没有 `.py` 后缀，只查 `clarify.py` 抓不到。
    # Ban the bare module name too: README's tree lists names without `.py`.
    "clarify",
    "wakeChain",
    "webSpeechProvider",
    "cloudAsrProvider",
    "ConsoleLibrary",
    "/api/voice/wake",
    "/api/voice/transcribe",
    "via=wake",
    "via=transcribe",
    "webspeech",
]

# 文档里以反引号引用的模块路径（`core/...py`，允许带 `:行号` 后缀）。
# Module paths cited in backticks (`core/...py`), optionally followed by `:line` refs.
_MODULE_RE = re.compile(r"`(core/[A-Za-z0-9_./-]+\.py)")


def _norm(path: str) -> str:
    """路径参数统一成 `{}` 并去掉尾部斜杠，便于文档与 OpenAPI 对比。"""
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/"))


def _api_paths(body: str) -> set[str]:
    """从一段文本里抽出反引号包裹的 `/api/...` 路径集合。"""
    return {_norm(m.group(1)) for m in re.finditer(r"`(/api/[^`\s·|]+)", body)}


def _actual_api_paths() -> set[str]:
    """后端真实提供的 HTTP + WebSocket 路径集合（归一化后）。"""
    actual = {_norm(p) for p in server.app.openapi()["paths"]}
    # WebSocket 路由不进 OpenAPI（FastAPI 只导出 HTTP 端点），从语音流路由表补上。
    # WebSocket routes never appear in OpenAPI (FastAPI exports HTTP only); add the
    # streaming router's paths.
    from core.api.voice import stream as voice_stream
    actual |= {_norm("/api" + r.path) for r in voice_stream.router.routes
               if type(r).__name__ == "APIWebSocketRoute"}
    return actual


def _readme_api_body() -> str:
    """README「API 端点」小节正文；解析不到时退回全文。"""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = re.search(r"^## API.*?\n(.*?)(?=^## )", text, re.S | re.M)
    return section.group(1) if section else text


def test_readme_api_paths_exist_in_openapi():
    """README 的 API 表与实际路由同步（删除/改名路由必须同时改文档）。"""
    documented = _api_paths(_readme_api_body())
    assert documented, "README API 表没有解析到任何端点"
    missing = sorted(documented - _actual_api_paths())
    assert not missing, f"README 列了不存在的端点: {missing}"


def test_wiki_api_paths_exist_in_openapi():
    """wiki/API.md 的端点表同样不得列出不存在的路由（此前只有 README 受检查）。"""
    text = (ROOT / "wiki" / "API.md").read_text(encoding="utf-8")
    section = re.search(r"^## 端点(.*?)(?=^## )", text, re.S | re.M)
    documented = _api_paths(section.group(1) if section else text)
    assert documented, "wiki/API.md 没有解析到任何端点"
    missing = sorted(documented - _actual_api_paths())
    assert not missing, f"wiki/API.md 列了不存在的端点: {missing}"


def test_removed_identifiers_not_in_current_docs():
    """已删除的路由/模块/通道标识不得回到当前文档。"""
    hits: list[str] = []
    for path in CURRENT_DOCS:
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN:
            if needle in text:
                hits.append(f"{path.relative_to(ROOT)}: {needle}")
    assert not hits, "当前文档仍引用已删除的标识:\n" + "\n".join(hits)


def test_doc_referenced_modules_exist():
    """当前文档引用的 `core/**.py` 必须真实存在：模块删除后文档不能还列着它。

    `docs/designs/10` 曾要求「删除 clarify.py」，但 README 目录树与 wiki 架构页
    继续引用它——只查死标识抓不到这种「目录树说谎」。占位示例（`core/tools/xxx.py`）
    跳过，不做存在性要求。
    """
    missing: list[str] = []
    found = 0
    for path in CURRENT_DOCS:
        text = path.read_text(encoding="utf-8")
        for m in _MODULE_RE.finditer(text):
            rel = m.group(1)
            if "xxx" in rel:  # 文档里的新建文件占位示例。Placeholder example.
                continue
            found += 1
            if not (ROOT / rel).is_file():
                line = text.count("\n", 0, m.start()) + 1
                missing.append(f"{path.relative_to(ROOT)}:{line}: {rel}")
    assert found >= 10, f"只解析到 {found} 个模块引用，_MODULE_RE 可能失效（门禁空转）"
    assert not missing, "当前文档引用了不存在的模块:\n" + "\n".join(missing)


def test_via_only_stream():
    """审计上传口径只允许 via=stream。"""
    bad: list[str] = []
    for path in CURRENT_DOCS:
        for m in re.finditer(r"via=([a-z][a-z-]*)", path.read_text(encoding="utf-8")):
            if m.group(1) != "stream":
                bad.append(f"{path.relative_to(ROOT)}: via={m.group(1)}")
    assert not bad, "非 stream 的 via= 口径:\n" + "\n".join(bad)
