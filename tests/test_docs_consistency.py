# -*- coding: utf-8 -*-
"""文档防漂移门禁（docs/designs/10 6.3）。

三件事：
1. README 的 API 表里列出的每个端点都必须真实存在于 OpenAPI；
2. 已删除的路由 / 文件 / 通道标识不得再出现在**当前文档**（README + wiki）；
3. `via=` 只允许 `stream`（流式会话是唯一上传口径）。

Docs drift gate (docs/designs/10 6.3): every endpoint listed in README's API table
must exist in the OpenAPI schema; deleted routes / file names / channel identifiers
must not reappear in current docs (README + wiki); and `via=` may only be `stream`
(the streaming session is the only upload path).
"""
import re
from pathlib import Path

import server

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DOCS = [ROOT / "README.md", *sorted((ROOT / "wiki").glob("*.md"))]

# 2026-11 已删除的标识：旧唤醒链路、任务库前端组件、旧上传通道。
# Identifiers removed in 2026-11: the legacy wake pipeline, the task-library component,
# and the old upload channels.
FORBIDDEN = [
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


def _norm(path: str) -> str:
    """路径参数统一成 `{}` 并去掉尾部斜杠，便于 README 与 OpenAPI 对比。"""
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/"))


def _readme_api_paths() -> set[str]:
    """README「API」小节里反引号包裹的 `/api/...` 路径集合。"""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = re.search(r"^## API.*?\n(.*?)(?=^## )", text, re.S | re.M)
    body = section.group(1) if section else text
    return {_norm(m.group(1)) for m in re.finditer(r"`(/api/[^`\s·|]+)", body)}


def test_readme_api_paths_exist_in_openapi():
    """README 的 API 表与实际路由同步（删除/改名路由必须同时改文档）。"""
    documented = _readme_api_paths()
    assert documented, "README API 表没有解析到任何端点"
    actual = {_norm(p) for p in server.app.openapi()["paths"]}
    # WebSocket 路由不进 OpenAPI（FastAPI 只导出 HTTP 端点），从语音流路由表补上。
    # WebSocket routes never appear in OpenAPI (FastAPI exports HTTP only); add the
    # streaming router's path (mounted under /api).
    from core.api.voice import stream as voice_stream
    actual |= {_norm("/api" + r.path) for r in voice_stream.router.routes
               if type(r).__name__ == "APIWebSocketRoute"}
    missing = sorted(documented - actual)
    assert not missing, f"README 列了不存在的端点: {missing}"


def test_removed_identifiers_not_in_current_docs():
    """已删除的路由/文件/通道标识不得回到当前文档。"""
    hits: list[str] = []
    for path in CURRENT_DOCS:
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN:
            if needle in text:
                hits.append(f"{path.relative_to(ROOT)}: {needle}")
    assert not hits, "当前文档仍引用已删除的标识:\n" + "\n".join(hits)


def test_via_only_stream():
    """审计上传口径只允许 via=stream。"""
    bad: list[str] = []
    for path in CURRENT_DOCS:
        for m in re.finditer(r"via=([a-z][a-z-]*)", path.read_text(encoding="utf-8")):
            if m.group(1) != "stream":
                bad.append(f"{path.relative_to(ROOT)}: via={m.group(1)}")
    assert not bad, "非 stream 的 via= 口径:\n" + "\n".join(bad)
