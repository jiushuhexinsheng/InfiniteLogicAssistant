# 后端异步化 + 原生工具调用 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将后端从同步 requests + stdlib http.server 重构为 FastAPI + httpx 异步，实现 OpenAI 原生 function-calling（`@tool` 注册中心 + ReAct 循环），`/api/ai/chat` 改为 SSE 流式，前端消费 SSE 并移除前端 JSON action 约定。

**Architecture:** 新增 `core/llm/stream.py`（httpx SSE→事件）、`core/llm/client.py`（重试+熔断+连接池）、`core/tools/`（@tool 注册中心 + 4 工具）、`core/agent.py`（ReAct）；`core/voice` 转 async httpx；`core/server.py` 重写为 FastAPI（SSE `/api/ai/chat` + 静态托管）；前端 `api.ts`/`useAssistant` 消费 SSE。

**Tech Stack:** Python 3.10 + httpx + FastAPI + uvicorn + duckduckgo-search + pyyaml/loguru；Vue 3 + TS。验证门槛：后端 `python -c import` + FastAPI 冒烟 + `npm run build`。

## Global Constraints

- 对外 HTTP 端点路径不变：`/api/ping` `/api/config` `/api/ai/chat` `/api/voice/transcribe`。
- `main.py serve`（默认 8520）与 `main.py test` 命令保留。
- 配置 profile 机制保留（`resolve_llm_profile` / `resolve_asr_profile` / `resolve_tts_profile`）。
- `App.vue` 不改；前端语音链路（唤醒→ASR→LLM→播报）语义不变。
- 新增依赖必须补入 `scripts/libs/` 离线 wheel（`install_deps.bat` 用 `--find-links`）。
- 每任务结束后端 `python -c "import core.server"` + 前端 `npm run build` 应能通过（任务相关范围）。
- 参考项目模式：`@tool` 纯 stdlib（inspect+typing），不引 pydantic。

---

## 阶段 A — 异步地基

### Task 1: 依赖安装 + requirements + 离线 wheel

**Files:**
- Modify: `requirements.txt`
- Modify: `scripts/libs/`（新增离线 wheel）

- [ ] **Step 1: 更新 `requirements.txt`**

```text
# 无限逻辑·语音助手 依赖
# 离线安装: python -m pip install --no-index --find-links=scripts\libs -r requirements.txt

httpx>=0.27.0
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
duckduckgo-search>=6.0.0
pyyaml>=6.0
loguru>=0.7.0
```

（`requests` 移除：LLM/ASR/TTS 全转 httpx；若 `start.bat`/`main.py` 仍引用 requests 则在对应任务处理。）

- [ ] **Step 2: 本地安装**

Run: `python -m pip install httpx "fastapi>=0.110" "uvicorn[standard]>=0.27" "duckduckgo-search>=6.0"`
Expected: 安装成功

- [ ] **Step 3: 下载离线 wheel 到 `scripts/libs/`**

Run: `python -m pip download httpx "fastapi>=0.110" "uvicorn[standard]>=0.27" "duckduckgo-search>=6.0" -d scripts/libs`
Expected: 依赖全部 wheel 落入 `scripts/libs/`

- [ ] **Step 4: 提交**

```bash
git add requirements.txt scripts/libs
git commit -m "feat: 新增 httpx/fastapi/uvicorn/duckduckgo-search 依赖与离线 wheel"
```

---

### Task 2: 配置新增 agent / llm_client 段

**Files:**
- Modify: `core/config.py`

**Interfaces:**
- Produces: 新增配置键（均带默认值）：`agent_recursion_limit`、`agent_max_history_messages`、`llm_retry_max`、`llm_retry_backoff_base`、`llm_retry_backoff_max`、`llm_circuit_breaker_threshold`、`llm_circuit_breaker_cooldown`、`llm_request_timeout`、`tool_search_max_results`、`weather_timeout`。

- [ ] **Step 1: `DEFAULTS` 增加配置**

在 `DEFAULTS` 字典中新增：

```python
"agent": {
    "recursion_limit": 6,
    "max_history_messages": 40,
},
"llm_client": {
    "retry_max": 3,
    "retry_backoff_base": 0.5,
    "retry_backoff_max": 10.0,
    "circuit_breaker_threshold": 5,
    "circuit_breaker_cooldown": 30.0,
    "request_timeout": 60,
},
"tools": {
    "search_max_results": 5,
    "weather_timeout": 10,
},
```

- [ ] **Step 2: 验证**

Run: `python -c "from core.config import cfg; print(cfg('agent.recursion_limit'), cfg('tools.search_max_results'))"`
Expected: `6 5`

- [ ] **Step 3: 提交**

```bash
git add core/config.py
git commit -m "feat: 配置新增 agent/llm_client/tools 段"
```

---

### Task 3: `core/llm/stream.py` — 异步 stream_chat

**Files:**
- Create: `core/llm/stream.py`

**Interfaces:**
- Produces: `async stream_chat(messages, tools=None, *, profile=None, client=None) -> AsyncIterator[dict]`
  - 事件：`content_delta` / `reasoning_delta` / `tool_call_delta` / `done`（`message` 含完整 assistant message）
  - `profile` 缺省用 `resolve_llm_profile()[1]`。

- [ ] **Step 1: 创建 `core/llm/stream.py`**

```python
# -*- coding: utf-8 -*-
"""异步 LLM 流式客户端 — httpx 解析 SSE → 事件流（参照 InfiniteLogic src/llm.py）

事件:
    content_delta    {"type":"content_delta","text":str}
    reasoning_delta  {"type":"reasoning_delta","text":str}
    tool_call_delta  {"type":"tool_call_delta","index":int,"id":str|None,"name":str,"arguments":str}
    done             {"type":"done","message":{role,content,reasoning_content?,tool_calls?}}
"""
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.config import resolve_llm_profile


def _build_payload(profile: dict, messages: list, tools=None) -> dict:
    payload = {
        "model": profile.get("model", ""),
        "messages": messages,
        "temperature": profile.get("temperature", 0.7),
        "max_tokens": profile.get("max_tokens", 4096),
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return payload


def _headers(profile: dict) -> dict:
    h = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if profile.get("api_key"):
        h["Authorization"] = f"Bearer {profile['api_key']}"
    return h


def _accumulate_tool_calls(buffer: dict, tc: dict) -> None:
    idx = tc.get("index", 0)
    if idx not in buffer:
        buffer[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
    slot = buffer[idx]
    if tc.get("id"):
        slot["id"] = tc["id"]
    fn = tc.get("function") or {}
    if fn.get("name"):
        slot["function"]["name"] += fn["name"]
    if fn.get("arguments"):
        slot["function"]["arguments"] += fn["arguments"]


async def stream_chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    *,
    profile: dict | None = None,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[dict]:
    """流式调用 LLM，逐 chunk yield 事件；最后 yield done（含完整 message）。"""
    if profile is None:
        _, profile = resolve_llm_profile()
    url = f"{profile.get('endpoint', '').rstrip('/')}{profile.get('chat_path', '/v1/chat/completions')}"
    payload = _build_payload(profile, messages, tools)
    timeout = float(profile.get("timeout", 60) or 60)

    content_buf: list[str] = []
    reasoning_buf: list[str] = []
    tool_buf: dict = {}

    own = None
    if client is None:
        own = httpx.AsyncClient(timeout=timeout)
        client = own
    try:
        async with client.stream("POST", url, headers=_headers(profile), json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                reasoning = delta.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning:
                    reasoning_buf.append(reasoning)
                    yield {"type": "reasoning_delta", "text": reasoning}

                content = delta.get("content")
                if isinstance(content, str) and content:
                    content_buf.append(content)
                    yield {"type": "content_delta", "text": content}

                for tc in delta.get("tool_calls") or []:
                    _accumulate_tool_calls(tool_buf, tc)
                    yield {
                        "type": "tool_call_delta",
                        "index": tc.get("index", 0),
                        "id": tc.get("id"),
                        "name": (tc.get("function") or {}).get("name") or "",
                        "arguments": (tc.get("function") or {}).get("arguments") or "",
                    }

        message: dict = {"role": "assistant", "content": "".join(content_buf)}
        if reasoning_buf:
            message["reasoning_content"] = "".join(reasoning_buf)
        if tool_buf:
            message["tool_calls"] = [tool_buf[i] for i in sorted(tool_buf)]
        yield {"type": "done", "message": message}
    finally:
        if own is not None:
            await own.aclose()
```

- [ ] **Step 2: 验证**

Run: `python -c "from core.llm.stream import stream_chat; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 提交**

```bash
git add core/llm/stream.py
git commit -m "feat: 异步 stream_chat — httpx SSE 解析（content/reasoning/tool_call/done）"
```

---

### Task 4: `core/voice/__init__.py` — ASR/TTS 转 async httpx

**Files:**
- Modify: `core/voice/__init__.py`

**Interfaces:**
- Produces: `ASRClient.transcribe_base64` → `async`；`TTSClient.speak` → `async`；模块级 `get_asr()` / `get_tts()` 不变。

- [ ] **Step 1: ASR 转 async**

- `requests.post` → `await httpx.AsyncClient(timeout=...).post(url, json=..., headers=...)`
- `transcribe_base64` 改为 `async def`；`raise_for_status`；返回 `choices[0].message.content`

- [ ] **Step 2: TTS 转 async**

- `requests.post` → async httpx；`_speak` 改 `async def`；`speak` 改 `async def`（catch 返回 False）
- `_play_audio` 保持不变（写临时文件 + `start` 播放）

- [ ] **Step 3: 更新引用**

`server.py` / `main.py` 中调用 ASR/TTS 处需 `await`（在 Task 5/6 一并处理；本任务先改模块本身）。

- [ ] **Step 4: 验证**

Run: `python -c "from core.voice import get_asr, get_tts; import inspect; print(inspect.iscoroutinefunction(get_asr().transcribe_base64))"`
Expected: `True`

- [ ] **Step 5: 提交**

```bash
git add core/voice/__init__.py
git commit -m "refactor: ASR/TTS 转 async httpx"
```

---

### Task 5: `core/server.py` 重写为 FastAPI

**Files:**
- Modify: `core/server.py`（整体重写）

**Interfaces:**
- Produces: `app`（FastAPI 实例）；`start_server(host, port, open_browser)` 用 uvicorn 启动。
- Consumes: `core.llm.stream` 暂未用；`/api/ai/chat` 过渡期保留旧同步 LLMClient（经 `asyncio.to_thread`）。

- [ ] **Step 1: 重写为 FastAPI**

```python
# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — FastAPI 异步服务（静态托管 + /api/*）"""
import json
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core.config import cfg, ensure_dirs, is_llm_configured, is_asr_configured, resolve_llm_profile, resolve_asr_profile, ROOT_DIR
from core.logger import logger

app = FastAPI(title="无限逻辑·语音助手")

WEB_DIST_DIR = ROOT_DIR / "web" / "dist"


@app.get("/api/ping")
async def ping():
    from datetime import datetime
    return {"ok": True, "time": datetime.now().isoformat()}


@app.get("/api/config")
async def config():
    return {
        "llm_available": is_llm_configured(),
        "llm_profile": resolve_llm_profile()[0],
        "asr_available": is_asr_configured(),
        "asr_profile": resolve_asr_profile()[0],
        "wake_word": cfg("voice.wake_word", {}),
        "vad": cfg("voice.vad", {}),
    }


@app.post("/api/voice/transcribe")
async def voice_transcribe(request: Request):
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
        return {"ok": True, "text": text}
    except Exception as e:
        logger.error("voice_transcribe: {}", e)
        return JSONResponse({"ok": False, "error": str(e)})


# ── /api/ai/chat：过渡期同步调用旧 LLM（Phase C 改 SSE）──
def _chat_sync(params: dict) -> dict:
    from core.llm import get_llm
    llm = get_llm()
    if not llm.available():
        return {"ok": False, "error": "LLM 未配置"}
    try:
        result = llm._call(params.get("messages", []))
        return {"ok": True, "text": result}
    except Exception as e:
        logger.error("ai_chat 失败: {} | {} {}", e, llm.provider, llm.model)
        return {"ok": False, "error": str(e)}


@app.post("/api/ai/chat")
async def ai_chat(request: Request):
    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    return await asyncio.to_thread(_chat_sync, params)


# ── 静态托管 web/dist（SPA 兜底）──
def _mount_static():
    if not WEB_DIST_DIR.is_dir():
        return
    app.mount("/", StaticFiles(directory=str(WEB_DIST_DIR), html=True), name="static")


_mount_static()


def start_server(host: str = "", port: int = 0, open_browser: bool = True):
    import asyncio
    import uvicorn
    host = host or cfg("server.host", "127.0.0.1")
    port = port or cfg("server.port", 8520)
    open_browser = open_browser and cfg("server.open_browser", True)
    ensure_dirs()
    logger.info("服务已启动: http://{}:{}", host, port)
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(f"http://{host}:{port}")), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
```

> 注：`import asyncio` 与 `import json`/`unquote` 按需放顶部；`StaticFiles(html=True)` 会优先 `index.html`。SPA 路由兜底：若需要非根路径回退 index.html，可用 `@app.get("/{full_path:path}")` 兜底路由（Phase C 一并处理）。

- [ ] **Step 2: 验证**

Run: `python -c "import core.server; print('ok')"` 且随机端口起服务冒烟 ping/config。
Expected: 通过

- [ ] **Step 3: 提交**

```bash
git add core/server.py
git commit -m "refactor: server.py 重写为 FastAPI（ping/config/transcribe 异步 + 静态托管，ai/chat 过渡）"
```

---

### Task 6: `main.py` serve/test 适配 async

**Files:**
- Modify: `main.py`

- [ ] **Step 1: serve 保持**

`cmd_serve()` → `start_server()`（接口不变）。

- [ ] **Step 2: test 适配 async**

`cmd_test()` 改为 `asyncio.run(_cmd_test())`；LLM 测试用 `get_llm_client().retry_stream_chat`（Phase C 后接；过渡期用 `asyncio.run(stream_chat)` 消费 `done`）；ASR 测试 `await asr.transcribe_base64(...)`。

- [ ] **Step 3: 验证**

Run: `python -c "import main; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 提交**

```bash
git add main.py
git commit -m "refactor: main.py serve/test 适配 async"
```

---

## 阶段 B — 工具层

### Task 7: `core/tools/base.py` — @tool 注册中心

**Files:**
- Create: `core/tools/base.py`

**Interfaces:**
- Produces: `@tool(description)` 装饰器、`_ToolRegistry`、`TOOLS` 单例；`TOOLS.schemas()` / `TOOLS.call(name,args)` / `TOOLS.acall(name,args)`。

- [ ] **Step 1: 创建 `core/tools/base.py`**

```python
# -*- coding: utf-8 -*-
"""工具装饰器与注册中心 — @tool 自动推导 OpenAI schema（参照 InfiniteLogic src/tools/base.py）

用法:
    @tool("获取当前日期时间")
    def get_datetime() -> str: ...

    TOOLS.schemas()          # → OpenAI tools 数组
    await TOOLS.acall(name, args)  # async 执行；异常转 "Error: ..." 字符串
"""
import asyncio
import inspect
from typing import Any, Callable, get_type_hints

ToolFunc = Callable[..., Any]


class _ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, name: str, func: ToolFunc, schema: dict[str, Any]) -> None:
        self._tools[name] = {"func": func, "schema": schema}

    def schemas(self) -> list[dict[str, Any]]:
        return [t["schema"] for t in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def call(self, name: str, args: dict[str, Any]) -> str:
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"
        func = self._tools[name]["func"]
        try:
            if asyncio.iscoroutinefunction(func):
                return f"Error: '{name}' is async; use acall()"
            return _to_string(func(**args))
        except Exception as exc:
            return f"Error in {name}: {exc}"

    async def acall(self, name: str, args: dict[str, Any]) -> str:
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"
        func = self._tools[name]["func"]
        try:
            if asyncio.iscoroutinefunction(func):
                return _to_string(await func(**args))
            return _to_string(await asyncio.to_thread(lambda: func(**args)))
        except Exception as exc:
            return f"Error in {name}: {exc}"


TOOLS = _ToolRegistry()


def _to_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


def _python_type_to_json(py_type: Any) -> dict[str, Any]:
    mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
    }
    return mapping.get(py_type, {"type": "string"})


def _build_schema(func: ToolFunc, description: str) -> dict[str, Any]:
    sig = inspect.signature(func)
    hints = get_type_hints(func)
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        prop = _python_type_to_json(hints.get(name, str))
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            prop["default"] = param.default
        properties[name] = prop
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def tool(description: str | None = None) -> Callable[[ToolFunc], ToolFunc]:
    def decorator(func: ToolFunc) -> ToolFunc:
        desc = description
        if desc is None:
            doc = (func.__doc__ or "").strip()
            desc = doc.splitlines()[0] if doc else func.__name__
        TOOLS.register(func.__name__, func, _build_schema(func, desc))
        return func
    return decorator
```

- [ ] **Step 2: 验证**

Run: `python -c "from core.tools.base import TOOLS, tool; @tool('t'); def f(a: int)->int: return a; print(TOOLS.schemas())"`
Expected: 打印含 `{"name":"f","parameters":...}` 的 schema

- [ ] **Step 3: 提交**

```bash
git add core/tools/base.py
git commit -m "feat: @tool 注册中心 — 签名推导 OpenAI schema + async 执行"
```

---

### Task 8: 内置工具 + `core/tools/__init__.py`

**Files:**
- Create: `core/tools/datetime_tool.py`、`calculator.py`、`search.py`、`weather.py`、`__init__.py`

**Interfaces:**
- Produces: 4 个注册工具；`core/tools/__init__.py` 导入触发注册并导出 `TOOLS`。

- [ ] **Step 1: `datetime_tool.py`**

```python
# -*- coding: utf-8 -*-
"""当前日期时间工具"""
from datetime import datetime
from core.tools.base import tool


@tool("获取当前日期与时间，返回中文格式")
def get_datetime() -> str:
    return datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
```

- [ ] **Step 2: `calculator.py`（安全算术）**

```python
# -*- coding: utf-8 -*-
"""安全算术计算器 — ast 白名单求值，禁 exec/eval"""
import ast
import operator
from core.tools.base import tool

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("不支持的表达式")


@tool("安全计算数学表达式（如 '2+3*4'）")
def calculate(expression: str) -> str:
    try:
        return str(_safe_eval(ast.parse(expression, mode="eval")))
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 3: `search.py`（duckduckgo）**

```python
# -*- coding: utf-8 -*-
"""duckduckgo 联网搜索"""
from core.config import cfg
from core.tools.base import tool


@tool("联网搜索网页，返回标题/链接/摘要")
def web_search(query: str) -> str:
    from duckduckgo_search import DDGS
    try:
        results = DDGS().text(query, max_results=cfg("tools.search_max_results", 5))
    except Exception as exc:
        return f"Error: {exc}"
    if not results:
        return "未找到结果"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title','')}\n   {r.get('href','')}\n   {r.get('body','')[:120]}")
    return "\n".join(lines)
```

- [ ] **Step 4: `weather.py`（wttr.in 免 key）**

```python
# -*- coding: utf-8 -*-
"""wttr.in 天气（免 key）"""
import httpx
from core.config import cfg
from core.tools.base import tool


@tool("查询城市天气，参数 city 为城市名（中文或拼音）")
async def get_weather(city: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=cfg("tools.weather_timeout", 10)) as c:
            r = await c.get(f"https://wttr.in/{city}?format=3&lang=zh")
            r.raise_for_status()
            return r.text.strip() or "暂无天气数据"
    except Exception as exc:
        return f"Error: {exc}"
```

- [ ] **Step 5: `core/tools/__init__.py`**

```python
# -*- coding: utf-8 -*-
"""工具模块 — 导入触发 @tool 注册到 TOOLS 单例"""
from core.tools import (  # noqa: F401
    calculator, datetime_tool, search, weather,
)
from core.tools.base import TOOLS  # noqa: F401
```

- [ ] **Step 6: 验证**

Run: `python -c "from core.tools import TOOLS; print([s['function']['name'] for s in TOOLS.schemas()])"`
Expected: `['calculate', 'get_datetime', 'get_weather', 'web_search']`

- [ ] **Step 7: 提交**

```bash
git add core/tools/
git commit -m "feat: 内置工具 datetime/calculate/search/weather + 注册入口"
```

---

### Task 9: 工具层 pytest 测试

**Files:**
- Create: `tests/test_tools.py`
- Modify: `requirements-dev.txt`（或新增）加 `pytest` / `pytest-asyncio`

**Interfaces:**
- Consumes: `core.tools`。

- [ ] **Step 1: 创建 `tests/test_tools.py`**

```python
# -*- coding: utf-8 -*-
import asyncio

import pytest

from core.tools import TOOLS
from core.tools.base import tool, _build_schema


def test_schemas_contain_all_tools():
    names = [s["function"]["name"] for s in TOOLS.schemas()]
    assert {"get_datetime", "calculate", "web_search", "get_weather"} <= set(names)


def test_schema_infers_required_and_type():
    @tool("t")
    def f(x: int, y: str = "a") -> str:
        return f"{x}{y}"
    s = _build_schema(f, "t")
    assert s["function"]["parameters"]["required"] == ["x"]
    assert s["function"]["parameters"]["properties"]["x"]["type"] == "integer"


def test_calculate_safe():
    assert TOOLS.call("calculate", {"expression": "2+3*4"}) == "14"
    assert TOOLS.call("calculate", {"expression": "__import__('os')"}).startswith("Error")


@pytest.mark.asyncio
async def test_acall_async_tool():
    result = await TOOLS.acall("calculate", {"expression": "10-3"})
    assert result == "7"
```

- [ ] **Step 2: 添加 dev 依赖并安装**

Run: `python -m pip install pytest pytest-asyncio`
Modify `requirements-dev.txt` 增加 `pytest>=8.0`、`pytest-asyncio>=0.23`。

- [ ] **Step 3: 运行测试**

Run: `python -m pytest tests/test_tools.py -q`
Expected: 全 PASS

- [ ] **Step 4: 提交**

```bash
git add tests/test_tools.py requirements-dev.txt
git commit -m "test: 工具注册中心与工具逻辑 pytest 测试"
```

---

## 阶段 C — ReAct + 加固

### Task 10: `core/llm/client.py` — LlmClient（重试 + 熔断 + 连接池）

**Files:**
- Create: `core/llm/client.py`

**Interfaces:**
- Produces: `class LlmClient`（`async retry_stream_chat(messages, tools)`）；`get_llm_client()` 单例；`CircuitBreakerOpenError` / `RetryExhaustedError`。
- Consumes: `core.llm.stream.stream_chat`、`core.config.cfg`。

- [ ] **Step 1: 创建 `core/llm/client.py`**

```python
# -*- coding: utf-8 -*-
"""异步 LLM 客户端 — 重试 + 熔断 + 连接池（参照 InfiniteLogic src/llm_client.py）"""
import asyncio
import random
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.config import cfg, resolve_llm_profile
from core.logger import logger
from core.llm.stream import stream_chat


class CircuitBreakerOpenError(Exception):
    pass


class RetryExhaustedError(Exception):
    pass


class CircuitBreaker:
    """熔断器：CLOSED --N失败--> OPEN --冷却--> HALF_OPEN --3成功--> CLOSED"""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._state = "CLOSED"
        self._failures = 0
        self._successes = 0
        self._opened_at = 0.0
        self._probe = False
        self._lock = asyncio.Lock()

    async def is_open(self) -> bool:
        async with self._lock:
            if self._state == "HALF_OPEN" and self._probe:
                return True
            if self._state != "OPEN":
                return False
            if time.monotonic() - self._opened_at >= self._cooldown:
                self._state = "HALF_OPEN"
                self._successes = 0
                self._probe = True
                return False
            return True

    async def record_success(self) -> None:
        async with self._lock:
            self._probe = False
            if self._state == "HALF_OPEN":
                self._successes += 1
                if self._successes >= 3:
                    self._state = "CLOSED"
                    self._failures = 0
            else:
                self._failures = 0

    async def record_failure(self) -> None:
        async with self._lock:
            self._probe = False
            if self._state == "HALF_OPEN":
                self._state = "OPEN"
                self._opened_at = time.monotonic()
                self._successes = 0
            elif self._state == "CLOSED":
                self._failures += 1
                if self._failures >= self._threshold:
                    self._state = "OPEN"
                    self._opened_at = time.monotonic()

    async def release_probe(self) -> None:
        async with self._lock:
            self._probe = False


_RETRYABLE = {429, 502, 503, 504}
_PERMANENT = {400, 401, 402, 403, 404, 422}


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in _RETRYABLE:
            return True
        if code in _PERMANENT:
            return False
        return code >= 500
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError)):
        return True
    return False


def _backoff(attempt: int) -> float:
    base = cfg("llm_client.retry_backoff_base", 0.5)
    cap = cfg("llm_client.retry_backoff_max", 10.0)
    raw = min(base * (2 ** (attempt - 1)), cap)
    return max(0.0, raw + raw * 0.25 * (2 * random.random() - 1))


class LlmClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        self._breaker = CircuitBreaker(
            failure_threshold=cfg("llm_client.circuit_breaker_threshold", 5),
            cooldown_seconds=cfg("llm_client.circuit_breaker_cooldown", 30.0),
        )

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=cfg("llm_client.request_timeout", 60),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http

    async def retry_stream_chat(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[dict]:
        if await self._breaker.is_open():
            raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        max_retries = cfg("llm_client.retry_max", 3)
        client = await self._get_http()
        emitted = False
        last_exc: Exception | None = None
        try:
            for attempt in range(max_retries + 1):
                try:
                    async for event in stream_chat(messages, tools, client=client):
                        if event["type"] in ("content_delta", "reasoning_delta", "tool_call_delta"):
                            emitted = True
                        yield event
                        if event["type"] == "done":
                            await self._breaker.record_success()
                            return
                except Exception as exc:
                    last_exc = exc
                    if not _is_retryable(exc):
                        raise
                    if emitted:
                        await self._breaker.record_failure()
                        raise RetryExhaustedError(f"LLM stream failed after partial output: {exc}") from exc
                    if attempt >= max_retries:
                        await self._breaker.record_failure()
                        raise RetryExhaustedError(f"LLM call failed after {max_retries} retries: {exc}") from exc
                    wait = _backoff(attempt + 1)
                    logger.warning("LLM retry in {:.1f}s (attempt {}/{}): {}", wait, attempt + 1, max_retries, exc)
                    await asyncio.sleep(wait)
            raise RetryExhaustedError(f"LLM call failed: {last_exc}")
        finally:
            await self._breaker.release_probe()


_client: LlmClient | None = None


def get_llm_client() -> LlmClient:
    global _client
    if _client is None:
        _client = LlmClient()
    return _client
```

- [ ] **Step 2: 验证**

Run: `python -c "from core.llm.client import get_llm_client; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 提交**

```bash
git add core/llm/client.py
git commit -m "feat: LlmClient 重试+熔断+连接池（异步）"
```

---

### Task 11: `core/agent.py` — ReAct 循环

**Files:**
- Create: `core/agent.py`

**Interfaces:**
- Produces: `async run_agent(messages, tools=None) -> AsyncIterator[dict]`
  - 事件：`content_delta` / `reasoning_delta` / `tool_start` / `tool_end` / `done` / `error`
- Consumes: `get_llm_client()`、`core.tools.TOOLS`、`core.config`。

- [ ] **Step 1: 创建 `core/agent.py`**

```python
# -*- coding: utf-8 -*-
"""ReAct Agent 循环 — 原生 OpenAI function-calling（参照 InfiniteLogic src/agent.py）

流程: 调 LLM(tools) → 有 tool_calls 则执行并回喂 → 直到最终答案
事件: content_delta / reasoning_delta / tool_start / tool_end / done / error
"""
import json
from collections.abc import AsyncIterator
from typing import Any

from core.config import cfg
from core.llm.client import CircuitBreakerOpenError, RetryExhaustedError, get_llm_client
from core.logger import logger
from core.tools import TOOLS


def _trim_history(messages: list[dict], max_messages: int) -> list[dict]:
    if len(messages) <= max_messages:
        return messages
    system: list[dict] = []
    rest: list[dict] = []
    for m in messages:
        if m.get("role") == "system" and not rest:
            system.append(m)
        else:
            rest.append(m)
    keep = max(1, max_messages - len(system))
    tail = rest[-keep:]
    while tail and tail[0].get("role") == "tool":
        tail.pop(0)
    return system + tail


async def run_agent(messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[dict]:
    history = list(messages)
    recursion_limit = cfg("agent.recursion_limit", 6)
    max_history = cfg("agent.max_history_messages", 40)

    for step in range(recursion_limit):
        try:
            assistant_message: dict | None = None
            async for event in get_llm_client().retry_stream_chat(
                _trim_history(history, max_history), tools=tools or TOOLS.schemas()
            ):
                etype = event["type"]
                if etype == "reasoning_delta":
                    yield {"type": "reasoning_delta", "text": event["text"]}
                elif etype == "content_delta":
                    yield {"type": "content_delta", "text": event["text"]}
                elif etype == "tool_call_delta":
                    pass  # UI 等完整 tool_start/tool_end
                elif etype == "done":
                    assistant_message = event["message"]
        except CircuitBreakerOpenError:
            yield {"type": "error", "message": "服务暂时不可用，请稍后重试"}
            return
        except RetryExhaustedError as exc:
            logger.error("LLM retries exhausted: {}", exc)
            yield {"type": "error", "message": f"LLM 调用失败: {exc}"}
            return
        except Exception as exc:
            logger.error("LLM call failed: {}", exc)
            yield {"type": "error", "message": f"LLM 调用失败: {exc}"}
            return

        if assistant_message is None:
            yield {"type": "error", "message": "LLM 返回空消息"}
            return

        history.append(assistant_message)
        tool_calls = assistant_message.get("tool_calls") or []
        if not tool_calls:
            yield {"type": "done"}
            return

        # 执行工具调用（串行）
        for tc in tool_calls:
            name = tc["function"]["name"]
            raw = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_start", "name": name, "args": args}
            logger.info("tool_call step={} name={} args={}", step, name, args)
            result = await TOOLS.acall(name, args)
            status = "error" if result.startswith("Error") else "ok"
            yield {"type": "tool_end", "name": name, "status": status, "output": result}
            history.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})

    yield {"type": "error", "message": f"工具循环超出上限（{recursion_limit} 步）"}
```

- [ ] **Step 2: 验证**

Run: `python -c "from core.agent import run_agent; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 提交**

```bash
git add core/agent.py
git commit -m "feat: ReAct 循环 run_agent — 工具执行回喂 + 历史裁剪"
```

---

### Task 12: `/api/ai/chat` 改 SSE（对接 agent）

**Files:**
- Modify: `core/server.py`

**Interfaces:**
- Produces: `POST /api/ai/chat` 返回 `StreamingResponse`（`text/event-stream`），事件序列化 `data: {json}\n\n`。
- Consumes: `run_agent`。

- [ ] **Step 1: 替换 `ai_chat` 为 SSE**

```python
import asyncio
import json as _json

from fastapi.responses import StreamingResponse


def _sse(payload: dict) -> str:
    return f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/api/ai/chat")
async def ai_chat(request: Request):
    body = await request.body()
    try:
        params = _json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    messages = params.get("messages", [])

    from core.agent import run_agent
    from core.config import is_llm_configured
    if not is_llm_configured():
        return JSONResponse({"ok": False, "error": "LLM 未配置"})

    async def event_stream():
        async for evt in run_agent(messages):
            yield _sse(evt)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 2: SPA 兜底路由**

在静态托管之外增加兜底（非 /api、非静态文件 → index.html）：

```python
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"ok": False, "error": f"未知接口: /{full_path}"}, status_code=404)
    idx = WEB_DIST_DIR / "index.html"
    if idx.is_file():
        return FileResponse(str(idx))
    return JSONResponse({"ok": False, "error": "前端未构建"}, status_code=404)
```

（同时移除 Task 5 的 `app.mount("/", StaticFiles...)`，改为按需 `FileResponse`，避免与兜底路由冲突。）

- [ ] **Step 3: 验证**

Run: 起服务 `python -c "import uvicorn, core.server; uvicorn.run(core.server.app, host='127.0.0.1', port=0)"`（或随机端口冒烟），`curl -N -X POST /api/ai/chat -d '{"messages":[...]}'` 观察 SSE 流。
Expected: `data: {...}` 事件流

- [ ] **Step 4: 提交**

```bash
git add core/server.py
git commit -m "feat: /api/ai/chat 改 SSE（对接 run_agent）+ SPA 兜底路由"
```

---

## 阶段 D — 前端 SSE 消费

### Task 13: `api.ts` streamChat + `useAssistant` 消费 SSE + 移除前端 JSON action

**Files:**
- Modify: `web/src/api.ts`
- Modify: `web/src/composables/useAssistant.ts`

**Interfaces:**
- Produces: `api.streamChat(messages, handlers)`；`useAssistant.handleLLM` 改为消费 SSE；删除 `SYSTEM_PROMPT` JSON action 约定与 `handleAction` 前端分发（保留 `retryTool`/`cancelTool` 接口）。

- [ ] **Step 1: `api.ts` 新增 `streamChat`**

```ts
export interface ChatHandlers {
  onContent: (text: string) => void
  onReasoning?: (text: string) => void
  onToolStart?: (name: string, args: Record<string, any>) => void
  onToolEnd?: (name: string, status: string, output: string) => void
  onDone: () => void
  onError: (msg: string) => void
}

export async function streamChat(messages: unknown[], h: ChatHandlers): Promise<void> {
  try {
    const resp = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
    })
    if (!resp.ok || !resp.body) {
      let msg = `HTTP ${resp.status}`
      try { const e = await resp.json(); if (e?.error) msg = e.error } catch {}
      throw new Error(msg)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const line = block.split('\n').find(l => l.startsWith('data: '))
        if (!line) continue
        const data = line.slice(6).trim()
        if (data === '[DONE]') break
        let evt: any
        try { evt = JSON.parse(data) } catch { continue }
        switch (evt.type) {
          case 'content_delta': h.onContent(evt.text); break
          case 'reasoning_delta': h.onReasoning?.(evt.text); break
          case 'tool_start': h.onToolStart?.(evt.name, evt.args || {}); break
          case 'tool_end': h.onToolEnd?.(evt.name, evt.status, evt.output || ''); break
          case 'done': h.onDone(); return
          case 'error': h.onError(evt.message || '出错'); return
        }
      }
    }
    h.onDone()
  } catch (e: any) {
    h.onError(e?.message || String(e))
  }
}
```

- [ ] **Step 2: `useAssistant.handleLLM` 改为消费 SSE**

- 删除 `SYSTEM_PROMPT` 的 `{"action":...}` 说明，改为："你叫小逻，用中文简洁回复。可用工具会由系统注入。"
- `handleLLM(userText)` 重构：
  - 构建 `history`（system + 最近消息）不变
  - 调 `streamChat(history, handlers)`
  - `onContent(text)`：累积 `acc`；新建 assistant 消息（或更新最后一条）文本；`partialText.value = acc`
  - `onToolStart(name,args)`：在**当前 assistant 消息**的 `toolCalls` 追加 `{id:genId(), name, args, status:'running'}`
  - `onToolEnd(name,status,output)`：找到该消息最后一个匹配 tool call，置 `status = status==='ok'?'done':'failed'`、`result = output`
  - `onDone`：`state='done'`、`speakText(acc)`
  - `onError`：`state='error'`、system 消息提示
- 删除 `handleAction` 前端分发（工具由后端执行）；保留 `retryTool`/`cancelTool`（仅操作本地 toolCalls 状态，重试可标记"由后端重跑"占位）
- `ToolCall` 的 `status` 类型保留 `pending|running|done|failed`

- [ ] **Step 3: 验证**

Run: `cd web && npm run build`
Expected: PASS（vue-tsc + vite）

- [ ] **Step 4: 提交**

```bash
git add web/src/api.ts web/src/composables/useAssistant.ts
git commit -m "refactor: 前端改 SSE 流式聊天 — streamChat 消费 + 移除 JSON action 约定"
```

---

### Task 14: 最终验证与清理

**Files:**
- 无新增。

- [ ] **Step 1: 全量回归**

- 后端：`python -m pytest tests/ -q`；`python -c "import core.server, core.agent, core.tools, main"` 通过
- 前端：`npm run build` 通过
- 冒烟：起服务，`/api/ping` `/api/config` `/api/voice/transcribe` 可用；`/api/ai/chat` 出 SSE

- [ ] **Step 2: 清理旧同步残留**

- grep `requests.` 于 `core/`、`main.py` → 应无残留（requests 已完全移除）
- 旧 `core/llm/__init__.py` 的同步 `LLMClient`/`get_llm`：若 `main.py test` 不再用则删除；`server.py` 过渡引用已移除

- [ ] **Step 3: 浏览器冒烟**

`start.bat`（或 `python main.py serve`），验证：语音链路、文字输入、流式回复、工具时间轴（触发工具时）。

- [ ] **Step 4: 提交（如有剩余调整）**

```bash
git add -A
git commit -m "refactor: 异步化收尾清理"
```

---

## Self-Review

**Spec coverage:**
- 异步地基（FastAPI + httpx + stream_chat + voice 异步 + main 适配）：Task 1-6 ✓
- 工具层（@tool 注册中心 + datetime/calculate/search/weather + 测试）：Task 7-9 ✓
- ReAct + 加固（LlmClient 重试/熔断 + run_agent + SSE 端点）：Task 10-12 ✓
- 前端 SSE 消费 + 移除 JSON action：Task 13 ✓
- 离线 wheel / 端点不变 / profile 保留 / 语音链路不变：Global Constraints ✓

**Placeholder scan:** 无 TBD；Task 13 的 retry/cancel 后端重跑标注为占位（仅本地状态操作），后续可接。

**Type consistency:** `stream_chat` 事件类型与 `run_agent`/SSE/前端 `streamChat` 事件名一致（content_delta/reasoning_delta/tool_start/tool_end/done/error）；`TOOLS.schemas()/acall` 在 Task 7/11 一致；`LlmClient.retry_stream_chat` 在 Task 10/11 一致。
