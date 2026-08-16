# 语音智能体收敛与清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收敛双 agent 入口到唯一编排管线（前后端全面切换），删除旧 ReAct 入口与桌面唤醒死代码，让 RAG 索引在启动时按需自动构建，并清除前端残留文件。

**Architecture:** 保持五层架构不变；把 `/api/voice/utter`（`run_pipeline`）升级为唯一 agent 路径——支持 `messages` 历史种子、流式 `tool_start/tool_end/usage/content_delta` 事件；前端对话从 `/api/ai/chat`（`run_agent`）切到 `/api/voice/utter`；删除 legacy ReAct 及其测试；RAG 索引在 server lifespan 按需重建；删除桌面唤醒相关代码/依赖/文档引用。

**Tech Stack:** Python 3.14 / FastAPI / httpx / pytest / Vue3 + TS + Vite。

**Spec:** `docs/superpowers/specs/2026-08-16-agent-convergence-cleanup-design.md`

## Global Constraints

- Python 3.14+；所有后端代码沿用现有 `core/` 结构与中文 docstring 风格。
- **向后兼容**：`/api/voice/utter` 现有事件类型（`task_state/content_delta/question/error/done`）只增不改；`run_pipeline` 与 `execute_task` 新增参数均为可选（默认 None），旧调用（runner.py、现有测试）不受影响。
- 删除任何文件前先 `grep` 确认无引用；删除纯死代码（不牵连运行链路）。
- TDD：每个任务先写失败测试，再实现，再验证通过，再提交。
- 前端验证 = `cd web && npm run build`（`vue-tsc` 类型检查 + vite 构建）。
- 后端验证 = `python -m pytest tests/ -q`（不联网：测试用 monkeypatch 桩）。

---

### Task 1: 清理前端残留 + 桌面唤醒死代码（#4 + #6）

**Files:**
- Delete: `web/lib/wake-word.js`、`web/lib/`（空目录）
- Delete: `core/voice/wake.py`、`scripts/voice_smoke.py`、`tests/test_voice_wake.py`
- Modify: `requirements.txt`（移除 vosk/sounddevice）
- Modify: `core/config.py`（移除 `voice.wake_word.local_model`）
- Modify: `config.yaml.example`（移除 `local_model` 行）
- Modify: `README.md`、`docs/architecture/roadmap.md`、`docs/architecture/01-voice-control-agent.md`（移除 wake.py 相关引用）

**Interfaces:**
- Consumes: 无。
- Produces: 工作区无 `vosk`/`sounddevice`/`WakeListener`/`is_stop_command` 引用；`voice.wake_word` 仅剩浏览器字段 `enabled/keyword/sensitivity/model_path`。

- [ ] **Step 1: 删除残留与死代码文件**

```bash
rm -f web/lib/wake-word.js
rmdir web/lib 2>/dev/null || true
rm -f core/voice/wake.py scripts/voice_smoke.py tests/test_voice_wake.py
```

- [ ] **Step 2: 移除依赖与配置字段**

`requirements.txt` 删除这两行：
```
vosk==0.3.45
sounddevice==0.5.5
```

`core/config.py` DEFAULTS 的 `voice.wake_word`（约 52-59 行）删除 `local_model` 及其注释，变为：
```python
        "wake_word": {
            "enabled": True,
            "keyword": "小逻小逻",
            "sensitivity": 0.5,
            "model_path": "/models/vosk-model-small-cn-0.22.tar.gz",  # 浏览器端 URL
        },
```

`config.yaml.example` 删除第 43 行（`local_model: ""` 那行）。

- [ ] **Step 3: grep 确认无残留引用**

```bash
grep -rn "vosk\|sounddevice\|WakeListener\|is_stop_command\|voice_smoke\|core.voice.wake\|local_model" core/ scripts/ tests/ server.py main.py requirements.txt config.yaml.example web/src/ --include=*.py --include=*.ts --include=*.vue --include=*.txt --include=*.yaml 2>/dev/null | grep -v __pycache__
```
Expected: 仅剩 `core/config.py` 的 `model_path`（浏览器）与前端 `wake-word.js` 内的 vosk WASM 用法（`web/public/lib/wake-word.js`，不在上述 glob 的 src 范围）。

- [ ] **Step 4: 同步文档**

`README.md` 的「桌面端说明」段（约 81-83 行）替换为：
```markdown
> **桌面端说明**：桌面原生悬浮球（PySide6）与本地常驻语音监听已暂停开发，桌面代码迁移至 `desktop-ball` 分支（不再回迁）。
> 当前语音交互由浏览器端 Vosk WASM 唤醒 + 后端 ASR 承担。
```

`README.md` 目录结构里两处：
- `core/voice/` 行 → `│   ├── voice/                 ASR / TTS（OpenAI 兼容）`
- `scripts/` 行 → `│   ├── scripts/                   辅助脚本（mcp_echo_server.py / verify_memory.py）+ 离线 wheel`

`docs/architecture/roadmap.md` 的「桌面端（暂停开发，不再迁移）」章节（约 23-32 行）删除 `core/voice/wake.py` 相关两句，改为：
```markdown
**决策**：桌面端**不再迁移回主分支**。当前语音交互由浏览器端 Vosk WASM 唤醒 + 后端 ASR 承担，
主分支以此为唯一语音入口；`desktop-ball` 分支保留为历史快照。
```

`docs/architecture/01-voice-control-agent.md`：把「实现状态」（约 10-11 行）、`voice/` 目录注释（约 63 行）、§3.1 语音两处（约 114-115 行）里涉及 `core/voice/wake.py`、`scripts/voice_smoke.py`、`tests/test_voice_wake.py` 的描述删去，替换为「桌面常驻监听已移除（代码在 `desktop-ball` 分支）」。

- [ ] **Step 5: 运行后端测试确认无破坏**

Run: `python -m pytest tests/ -q`
Expected: 全部 PASS（test_voice_wake.py 已被删除，其余不受影响）。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: 移除前端残留 web/lib 与桌面唤醒死代码（wake.py/voice_smoke/依赖/配置/文档）"
```

---

### Task 2: RAG 启动按需建索引（#5）

**Files:**
- Modify: `core/rag/indexer.py`（`index_sources` 加 `index_db` 参数）
- Modify: `core/rag/__init__.py`（新增 `maybe_rebuild_index`）
- Modify: `core/config.py`（DEFAULTS 加 `rag.auto_index`）
- Modify: `config.yaml.example`（加 `rag` 段）
- Modify: `server.py`（lifespan 调用）
- Modify: `tests/test_rag.py`、`tests/test_server.py`

**Interfaces:**
- Consumes: `core.config.ROOT_DIR`、`core.rag.INDEX_DB`、`core.rag.DEFAULT_SOURCES`、`core.rag.indexer.index_sources`。
- Produces: `async def maybe_rebuild_index(sources: list[Path] | None = None, index_db: Path | None = None) -> None`；`index_sources(sources, index_db=None)`（新可选参数，向后兼容）。`config.yaml` 新配置 `rag.auto_index`（默认 true）。

- [ ] **Step 1: 写失败测试（`tests/test_rag.py` 末尾追加）**

```python
@pytest.mark.asyncio
async def test_index_sources_hermetic_index_db(tmp_path):
    src = tmp_path / "src.md"
    src.write_text("## 主题\n\n内容", encoding="utf-8")
    db = tmp_path / "hermetic.db"
    await index_sources([src], index_db=db)
    import sqlite3
    conn = sqlite3.connect(str(db))
    try:
        n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        conn.close()
    assert n >= 1


@pytest.mark.asyncio
async def test_maybe_rebuild_missing_db(tmp_path, monkeypatch):
    from core.rag import maybe_rebuild_index
    import core.rag.retriever as retriever_mod
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    db = tmp_path / "index.db"
    await maybe_rebuild_index([src], index_db=db)
    assert db.exists()
    monkeypatch.setattr(retriever_mod, "INDEX_DB", db)
    hits = await retrieve("python")
    assert hits and any("Python" in h["text"] for h in hits)


@pytest.mark.asyncio
async def test_maybe_rebuild_when_stale(tmp_path, monkeypatch):
    import os
    import time
    from core.rag import maybe_rebuild_index
    import core.rag.retriever as retriever_mod
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    db = tmp_path / "index.db"
    await maybe_rebuild_index([src], index_db=db)
    src.write_text("## 系统\n\nPython 3.15 更新了", encoding="utf-8")
    os.utime(src, (time.time() + 2, time.time() + 2))
    await maybe_rebuild_index([src], index_db=db)
    monkeypatch.setattr(retriever_mod, "INDEX_DB", db)
    hits = await retrieve("3.15")
    assert hits and any("3.15" in h["text"] for h in hits)


@pytest.mark.asyncio
async def test_maybe_rebuild_skips_fresh(tmp_path):
    from core.rag import maybe_rebuild_index
    src = tmp_path / "env.md"
    src.write_text("## 系统\n\nPython 3.14", encoding="utf-8")
    db = tmp_path / "index.db"
    await maybe_rebuild_index([src], index_db=db)
    before = db.stat().st_mtime_ns
    await maybe_rebuild_index([src], index_db=db)  # 源未变 → 不应重建
    assert db.stat().st_mtime_ns == before
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_rag.py -q`
Expected: FAIL（`index_sources() got an unexpected keyword argument 'index_db'`、`ImportError: cannot import name 'maybe_rebuild_index'`）。

- [ ] **Step 3: 实现 `index_sources` 加 `index_db` 参数（`core/rag/indexer.py`）**

`index_sources` 函数体改为（其余不变）：
```python
async def index_sources(sources: list[Path], index_db: Path | None = None) -> None:
    """重建索引：把 sources（文件或目录）全部切块写入 sqlite。

    index_db 缺省用 INDEX_DB（core.rag 模块级）；测试可显式传入隔离的 db 路径。
    """
    db = Path(index_db) if index_db is not None else Path(INDEX_DB)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, section TEXT, text TEXT)")
        conn.execute("DELETE FROM chunks")
        count = 0
        for src in sources:
            for p in _iter_files(Path(src)):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for c in _chunk_text(text, str(p)):
                    conn.execute("INSERT INTO chunks (path, section, text) VALUES (?,?,?)",
                                 (c["path"], c["section"], c["text"]))
                    count += 1
    return count
```

- [ ] **Step 4: 实现 `maybe_rebuild_index`（`core/rag/__init__.py` 追加）**

`core/rag/__init__.py` 末尾追加（`Path` 需 import）：
```python
async def maybe_rebuild_index(sources: list[Path] | None = None, index_db: Path | None = None) -> None:
    """index.db 缺失或任一源文件比索引新时重建；best-effort（失败不抛出）。"""
    from core.rag.indexer import index_sources
    sources = sources if sources is not None else DEFAULT_SOURCES
    db = Path(index_db) if index_db is not None else Path(INDEX_DB)
    if not db.exists():
        await index_sources(sources, index_db=db)
        return
    try:
        index_mtime = db.stat().st_mtime
    except OSError:
        return
    stale = False
    for src in sources:
        p = Path(src)
        try:
            if p.is_file():
                if p.stat().st_mtime > index_mtime:
                    stale = True
                    break
            elif p.is_dir():
                newest = 0.0
                for f in p.rglob("*"):
                    if f.is_file() and f.suffix.lower() in (".md", ".txt", ".py", ".yaml", ".yml", ".json", ".toml"):
                        newest = max(newest, f.stat().st_mtime)
                if newest > index_mtime:
                    stale = True
                    break
        except OSError:
            continue
    if stale:
        await index_sources(sources, index_db=db)
```
文件头补 `from pathlib import Path`。

- [ ] **Step 5: 配置 + server 接入**

`core/config.py` DEFAULTS（`"mcp"` 键后）加：
```python
    "rag": {
        # 启动时按需重建索引：index.db 缺失或 environment.md/docs 更新时重建
        "auto_index": True,
    },
```

`config.yaml.example` 末尾（`mcp` 段后）加：
```yaml
# RAG 索引：启动时 index.db 缺失或源文件更新则自动重建；false 关闭自动构建
rag:
  auto_index: true
```

`server.py` lifespan 的 `yield` 之前追加：
```python
    # 启动时按需重建 RAG 索引（best-effort）
    try:
        if cfg("rag.auto_index", True):
            from core.rag import maybe_rebuild_index
            await maybe_rebuild_index()
    except Exception as e:
        logger.warning("RAG 索引构建失败: {}", e)
```

`tests/test_server.py` 的 `client` fixture（lifespan 会在 `with TestClient` 时触发 RAG 重建，测试要隔离）追加 monkeypatch：
```python
    monkeypatch.setattr(server_module, "cfg",
                        lambda path, default=None: False if path == "rag.auto_index" else server_module.cfg(path, default))
```

- [ ] **Step 6: 运行确认通过**

Run: `python -m pytest tests/test_rag.py tests/test_server.py -q`
Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add core/rag/ core/config.py config.yaml.example server.py tests/test_rag.py tests/test_server.py
git commit -m "feat: RAG 索引启动时按需自动重建（rag.auto_index 开关）"
```

---

### Task 3: 后端编排流式事件 + messages 历史种子（#3 后端增强）

**Files:**
- Modify: `core/orchestrator/pipeline.py`、`core/orchestrator/executor.py`
- Modify: `server.py`（`/api/voice/utter` 透传 `messages`）
- Modify: `tests/test_orchestrator_pipeline.py`、`tests/test_orchestrator_executor.py`、`tests/test_server.py`

**Interfaces:**
- Consumes: 现有 `EventQueueChannel`、`Session`、`StopController`、`Task`。
- Produces:
  - `run_pipeline(text, session, events, controller, channel=None, messages=None)`
  - `_chit_chat_reply(session, events, text)`（新签名）
  - `execute_task(task, session, cancel, events=None)`（新增可选 `events`）
  - `/api/voice/utter` 请求体新增可选 `messages`（`[{role, content}]`）
  - 新增 SSE 事件透传：`content_delta / usage / tool_start / tool_end`

- [ ] **Step 1: 写失败测试**

`tests/test_orchestrator_pipeline.py` 追加：
```python
@pytest.mark.asyncio
async def test_run_pipeline_seeds_messages(monkeypatch):
    from core.orchestrator.pipeline import run_pipeline
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Session
    from core.orchestrator.intent import IntentResult

    async def fake_judge(text):
        return IntentResult(type="chit_chat", summary="打招呼")

    async def fake_stream(messages, **kw):
        # 断言多轮历史被带入：最后一个 user 消息是当前输入
        assert messages[-1]["role"] == "user" and messages[-1]["content"] == "你好"
        assert any(m["content"] == "昨天聊过" for m in messages)
        yield {"type": "content_delta", "text": "你好呀"}
        yield {"type": "done", "message": {"role": "assistant", "content": "你好呀"}}

    monkeypatch.setattr("core.orchestrator.pipeline.judge_intent", fake_judge)
    monkeypatch.setattr("core.orchestrator.pipeline.stream_chat", fake_stream)
    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await run_pipeline(
        "你好", s, events, StopController(),
        messages=[{"role": "user", "content": "昨天聊过"}],
    )
    assert s.messages[-1]["content"] == "你好"
    assert any(m["content"] == "昨天聊过" for m in s.messages)
    assert (await events.get())["type"] == "task_state"
    assert (await events.get())["type"] == "content_delta"
    assert (await events.get())["type"] == "done"
```

`tests/test_orchestrator_executor.py` 追加：
```python
@pytest.mark.asyncio
async def test_execute_emits_streaming_events(monkeypatch):
    import asyncio
    fake = _FakeLLM([
        [_done(tool="calculate", args=json.dumps({"expression": "1+1"})),
         {"type": "usage", "usage": {"total_tokens": 5}}],
        [{"type": "content_delta", "text": "结果是 "},
         {"type": "content_delta", "text": "2"},
         _done(content="结果是 2")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    events: asyncio.Queue = asyncio.Queue()
    r = await execute_task(Task("t", "算 1+1", risk="read"), s, CancellationToken(), events)
    assert r["status"] == "done"
    evts = []
    while not events.empty():
        evts.append(events.get_nowait())
    types = [e["type"] for e in evts]
    assert "tool_start" in types and "tool_end" in types
    assert "usage" in types
    content = "".join(e.get("text", "") for e in evts if e["type"] == "content_delta")
    assert "结果是 2" in content
```

`tests/test_server.py`：
- `test_voice_utter_task_done` 的 `fake_execute` 签名改为 `async def fake_execute(task, session, cancel, events=None):`。
- 追加透传测试：
```python
def test_voice_utter_forwards_messages(client, monkeypatch):
    captured = {}

    async def fake_run(text, session, events, controller, channel=None, messages=None):
        captured["messages"] = messages
        await events.put({"type": "done"})

    monkeypatch.setattr(pipeline_mod, "run_pipeline", fake_run)
    resp = client.post("/api/voice/utter", json={
        "text": "hi",
        "messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
    })
    assert resp.status_code == 200
    assert captured["messages"] == [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_pipeline.py tests/test_orchestrator_executor.py tests/test_server.py -q`
Expected: FAIL（`run_pipeline() got an unexpected keyword argument 'messages'`、`execute_task() got an unexpected keyword argument 'events'`、server 透传失败）。

- [ ] **Step 3: 实现 `pipeline.py`**

`run_pipeline` 签名与开头改为：
```python
async def run_pipeline(text: str, session: Session, events: asyncio.Queue,
                       controller: StopController, channel: OperatorChannel | None = None,
                       messages: list[dict] | None = None) -> None:
    """完整编排，产出事件（以 done 事件收尾）。channel 缺省用 SSE 队列通道。

    messages 为前端多轮历史种子（含当前用户消息）；缺省时把 text 记为当前用户消息。
    """
    if channel is None:
        channel = EventQueueChannel(events, session.id)
    session.channel = channel
    if messages:
        session.messages = [
            m for m in messages
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)
        ]
        # 确保当前用户消息在末尾（调用方可能只传历史）
        if not session.messages or session.messages[-1].get("role") != "user" or session.messages[-1].get("content") != text:
            session.messages.append({"role": "user", "content": text})
    else:
        session.append("user", text)
    session.set_state(SessionState.UNDERSTANDING)
    await events.put({"type": "task_state", "state": "understanding", "session_id": session.id})

    intent = await judge_intent(text)
    if intent.type == "chit_chat":
        session.set_state(SessionState.CHIT_CHAT)
        try:
            await _chit_chat_reply(session, events, text)
        except Exception as e:
            await events.put({"type": "error", "message": str(e)})
        await events.put({"type": "done"})
        return
    ...
    result = await execute_task(task, session, controller.token, events)
```

`_chit_chat_reply` 改为（带入会话历史实现多轮）：
```python
async def _chit_chat_reply(session: Session, events: asyncio.Queue, text: str) -> None:
    messages = [{"role": "system", "content": "你是小逻，用中文简洁友好地回复。"}]
    messages.extend(session.summary(8))  # 含当前用户消息 → 多轮闲聊
    async for evt in stream_chat(messages):
        if evt["type"] == "content_delta":
            await events.put({"type": "content_delta", "text": evt["text"]})
```

- [ ] **Step 4: 实现 `executor.py`**

`execute_task` 签名改为 `async def execute_task(task: Task, session: Session, cancel: CancellationToken, events: asyncio.Queue | None = None) -> dict:`（顶部加 `import asyncio`，未引入则补）。

ReAct 分支上下文构建改为（替换原 `context`/`sys_prompt` 两行）：
```python
    max_steps = cfg("agent.recursion_limit", 12)
    # RAG + 长期记忆注入（失败不影响执行）
    context = ""
    try:
        context = await build_context(task.goal + " " + json.dumps(task.params, ensure_ascii=False))
    except Exception:
        pass
    # 对话历史（排除当前轮用户消息，供多轮任务上下文）
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
    sys_prompt = f"{_SYSTEM}\n\n" + "\n\n".join(context_lines) if context_lines else _SYSTEM
    history = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"任务目标：{task.goal}\n参数：{json.dumps(task.params, ensure_ascii=False)}"},
    ]
```

ReAct 循环内 LLM 事件转发（替换 `async for evt in get_llm_client().retry_stream_chat(...)` 块）：
```python
            async for evt in get_llm_client().retry_stream_chat(history, tools=TOOLS.schemas()):
                if evt["type"] == "done":
                    assistant_message = evt["message"]
                elif events is not None and evt["type"] in ("content_delta", "usage"):
                    await events.put(evt)
```

工具循环内发射事件（在 `name`/`args` 解析后、确认前插入；在 `result` 取得后插入）：
```python
                if events is not None:
                    await events.put({"type": "tool_start", "name": name, "args": args})
```
```python
                status = "error" if result.startswith("Error") else "ok"
                if events is not None:
                    await events.put({"type": "tool_end", "name": name, "status": status, "output": result[:500]})
```

- [ ] **Step 5: 实现 `server.py` `/api/voice/utter` 透传 messages**

在 `text` 校验后、`Session()` 创建前插入：
```python
    messages = params.get("messages")
    if not isinstance(messages, list):
        messages = None
```
把 `runner = asyncio.ensure_future(run_pipeline(text, session, events, controller))` 改为：
```python
    runner = asyncio.ensure_future(run_pipeline(text, session, events, controller, messages=messages))
```

- [ ] **Step 6: 运行确认通过**

Run: `python -m pytest tests/test_orchestrator_pipeline.py tests/test_orchestrator_executor.py tests/test_server.py -q`
Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add core/orchestrator/ server.py tests/
git commit -m "feat(编排): 管线支持 messages 历史种子 + 执行器流式 tool/usage/content 事件"
```

---

### Task 4: 前端对话切换到编排管线（#3 前端）

**Files:**
- Modify: `web/src/api.ts`、`web/src/composables/assistant/store.ts`、`web/src/composables/assistant/useChat.ts`、`web/src/composables/useAssistant.ts`
- Create: `web/src/components/assistant/QuestionCard.vue`
- Modify: `web/src/components/assistant/ChatInput.vue`、`web/src/styles/assistant.css`

**Interfaces:**
- Consumes: `streamUtter`（新签名）、`useAssistant()`（新增 `pendingQuestion`/`sendAnswer`）。
- Produces:
  - `streamUtter(text, h, opts?: { messages?: {role:string;content:string}[]; signal?: AbortSignal }): Promise<string>`
  - `UtterHandlers` 含 `onTaskState/onContent/onReasoning/onToolStart/onToolEnd/onUsage/onQuestion/onError/onDone(sessionId)/onAbort`
  - `store.ts`：`buildHistory()` 无 system；新增 `pendingQuestion`、`currentSessionId` ref
  - `useChat.ts`：`sendAnswer(text)`；`runTurn()` 用 `streamUtter`
  - 删除 `streamChat`、`ChatHandlers`、`SYSTEM_PROMPT`

- [ ] **Step 1: `web/src/api.ts` — 重写 `streamUtter`、删除 `streamChat`**

删除 `streamChat` 函数与 `ChatHandlers` 接口（第 39-106 行）。

把 `UtterHandlers` 与 `streamUtter` 替换为：
```ts
// ─── 编排 SSE：/api/voice/utter（唯一 agent 路径，含澄清/确认 question 事件）───

export interface UtterHandlers {
  onTaskState?: (s: TaskState) => void
  onContent?: (text: string) => void
  onReasoning?: (text: string) => void
  onToolStart?: (name: string, args: Record<string, any>) => void
  onToolEnd?: (name: string, status: string, output: string) => void
  onUsage?: (usage: TokenUsage) => void
  onQuestion?: (q: { question: string; session_id: string }) => void
  onError?: (msg: string) => void
  onDone?: (sessionId: string) => void
  /** 用户主动中止（AbortController.abort()），区别于 onError */
  onAbort?: () => void
}

/** 消费 /api/voice/utter 的 SSE 事件流；返回 session_id（供 answer/stop 用）。 */
export async function streamUtter(
  text: string,
  h: UtterHandlers,
  opts?: { messages?: { role: string; content: string }[]; signal?: AbortSignal },
): Promise<string> {
  let sessionId = ''
  const body: Record<string, unknown> = { text }
  if (opts?.messages?.length) body.messages = opts.messages
  try {
    const resp = await fetch(`${BASE}/voice/utter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: opts?.signal,
    })
    if (!resp.ok || !resp.body) {
      let msg = `HTTP ${resp.status}`
      try {
        const e = await resp.json()
        if (e?.error) msg = e.error
      } catch { /* not JSON */ }
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
        if (evt.session_id) sessionId = evt.session_id
        switch (evt.type) {
          case 'task_state': h.onTaskState?.(evt); break
          case 'content_delta': h.onContent?.(evt.text); break
          case 'reasoning_delta': h.onReasoning?.(evt.text); break
          case 'tool_start': h.onToolStart?.(evt.name, evt.args || {}); break
          case 'tool_end': h.onToolEnd?.(evt.name, evt.status, evt.output || ''); break
          case 'usage': h.onUsage?.(evt.usage); break
          case 'question': h.onQuestion?.({ question: evt.question, session_id: evt.session_id }); break
          case 'error': h.onError?.(evt.message); return sessionId
          case 'done': h.onDone?.(sessionId); return sessionId
        }
      }
    }
    h.onDone?.(sessionId)
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      h.onAbort?.()
      return sessionId
    }
    h.onError?.(e?.message || String(e))
  }
  return sessionId
}
```

- [ ] **Step 2: `web/src/composables/assistant/store.ts`**

删除 `SYSTEM_PROMPT` 常量（第 34-35 行）。

`buildHistory()`（第 90-108 行）替换为（去掉 system 注入，纯历史）：
```ts
// ── 多轮历史构建（system 由后端各自注入；工具结果拼入 assistant content）──
export function buildHistory(): { role: string; content: string }[] {
  const history: { role: string; content: string }[] = []
  for (const m of messages.value.slice(-6)) {
    if (m.role === 'user') history.push({ role: 'user', content: m.text })
    else if (m.role === 'assistant') {
      let content = m.text
      if (m.toolCalls?.length) {
        const results = m.toolCalls
          .map((tc) => `[工具 ${tc.name} 执行结果]\n${tc.result || ''}`)
          .join('\n\n')
        content = `${content}\n\n${results}`
      }
      history.push({ role: 'assistant', content })
    }
  }
  return history
}
```

在 `tokenUsage` 定义附近新增：
```ts
// 编排问答：待回答的澄清/确认问题 与 当前会话 id
export const pendingQuestion = ref('')
export const currentSessionId = ref('')
```

- [ ] **Step 3: `web/src/composables/assistant/useChat.ts` — 切到 `streamUtter`**

文件顶部 import 改为：
```ts
import { reactive } from 'vue'
import { api, streamUtter } from '../../api'
import { state, messages, tokenUsage, partialText, genId, addMessage, buildHistory, MAX_MESSAGES, pendingQuestion, currentSessionId } from './store'
import { speakText } from './useTts'
import type { ChatMessage, ToolCall } from './store'
```

`runTurn()` 整体替换为（`sendText`/`retryTool`/`cancelTool` 保持）。注意：编排管线按新话语驱动，**`retryTool` 末尾不再自动调 `runTurn()`**——重试后用户发新话语（如「继续」）即可，历史会随 `messages` 种子带入上下文：
```ts
// 消费编排 SSE 流（唯一 agent 路径；工具由后端执行，前端只展示）
export async function runTurn() {
  const last = messages.value[messages.value.length - 1]
  if (!last || last.role !== 'user') return  // 只对用户话语启动一轮
  const text = last.text
  state.value = 'thinking'
  const history = buildHistory()

  // 中止上一次未结束的流（防并发覆盖）
  abortController?.abort()
  abortController = new AbortController()

  let acc = ''
  let currentMsg: ChatMessage | null = null
  const toolAcc = reactive<ToolCall[]>([])
  const toolStartMap = new Map<string, number>()

  const ensureMsg = () => {
    if (!currentMsg) {
      const msg = { id: genId(), role: 'assistant' as const, text: '', toolCalls: toolAcc, timestamp: Date.now() }
      messages.value.push(msg)
      if (messages.value.length > MAX_MESSAGES) messages.value.shift()
      currentMsg = messages.value[messages.value.length - 1]
    }
    return currentMsg
  }

  let textFlushTimer: ReturnType<typeof setTimeout> | null = null
  const scheduleText = () => {
    if (textFlushTimer) return
    textFlushTimer = setTimeout(() => {
      textFlushTimer = null
      ensureMsg().text = acc
    }, 50)
  }
  const flushText = () => {
    if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
    if (acc) ensureMsg().text = acc
  }

  await streamUtter(text, {
    onTaskState: (s) => {
      if (s.session_id) currentSessionId.value = s.session_id
      if (s.state === 'understanding') state.value = 'thinking'
      else if (s.state === 'notify' || s.state === 'done') { /* 状态提示由消息文本呈现 */ }
    },
    onContent: (t) => {
      state.value = 'responding'
      acc += t
      partialText.value = acc
      scheduleText()
    },
    onReasoning: () => { /* 前端不展示思考过程，忽略 */ },
    onToolStart: (name, args) => {
      state.value = 'tool_calling'
      const id = genId()
      toolStartMap.set(id, Date.now())
      toolAcc.push({ id, name, args, status: 'running' })
      ensureMsg()
    },
    onToolEnd: (name, status, output) => {
      const tc = toolAcc.find(t => t.name === name && t.status === 'running')
      if (tc) {
        tc.status = status === 'ok' ? 'done' : 'failed'
        tc.result = output
        const st = toolStartMap.get(tc.id)
        if (st != null) tc.durationMs = Date.now() - st
        toolStartMap.delete(tc.id)
      }
    },
    onUsage: (u) => {
      tokenUsage.value.prompt_tokens = (tokenUsage.value.prompt_tokens || 0) + (u.prompt_tokens || 0)
      tokenUsage.value.completion_tokens = (tokenUsage.value.completion_tokens || 0) + (u.completion_tokens || 0)
      tokenUsage.value.total_tokens = (tokenUsage.value.total_tokens || 0) + (u.total_tokens || 0)
    },
    onQuestion: ({ question, session_id }) => {
      currentSessionId.value = session_id
      pendingQuestion.value = question
      state.value = 'thinking'
    },
    onDone: (sessionId) => {
      if (sessionId) currentSessionId.value = sessionId
      pendingQuestion.value = ''
      flushText()
      partialText.value = ''
      if (acc.trim()) speakText(acc)
      else if (toolAcc.length) speakText('已完成')
      state.value = 'done'
    },
    onAbort: () => {
      if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
      partialText.value = ''
      pendingQuestion.value = ''
      state.value = 'done'
    },
    onError: (msg) => {
      if (textFlushTimer) { clearTimeout(textFlushTimer); textFlushTimer = null }
      console.error('[Asst] LLM error:', msg)
      addMessage('system', '出错了: ' + msg)
      pendingQuestion.value = ''
      state.value = 'error'
    },
  }, { messages: history, signal: abortController.signal })
}

// ── 回答澄清/确认问题（解除后端 ask() 阻塞）──
export async function sendAnswer(text: string) {
  const t = text.trim()
  if (!t || !currentSessionId.value) return
  try {
    await api.answer(currentSessionId.value, t)
    pendingQuestion.value = ''
  } catch (e: any) {
    addMessage('system', '回答投递失败: ' + (e?.message || ''))
  }
}
```

`retryTool` 调整：保留 `api.callTool` 真实重跑 + 更新 `tc` 的部分，但**删除**末尾两行并改注释：
```ts
  tc.durationMs = Date.now() - startTs
  // 不再自动续轮：编排管线按新话语驱动，用户可发「继续」等新话语，历史随 messages 种子带入
```

- [ ] **Step 4: `web/src/composables/useAssistant.ts` — 门面暴露新状态/方法**

import 行改为：
```ts
import { sendText, retryTool, cancelTool, abortChat, sendAnswer } from './assistant/useChat'
import {
  state, messages, expanded, wakeEnabled, wakeKeyword, partialText, statusLine, tokenUsage,
  wakeConfig, vadConfig, clearMessages, pendingQuestion, currentSessionId,
} from './assistant/store'
```
返回对象新增：
```ts
    pendingQuestion,
    currentSessionId,
```
与：
```ts
    sendAnswer,
```

- [ ] **Step 5: 新增 `QuestionCard.vue` + 嵌入 `ChatInput.vue` + 样式**

创建 `web/src/components/assistant/QuestionCard.vue`：
```vue
<template>
  <div class="confirm-card">
    <div class="confirm-title">❓ 需要你回答</div>
    <p class="confirm-q">{{ question }}</p>
    <div class="confirm-row">
      <input v-model="answer" placeholder="输入回答后回车…" @keydown.enter="submit" />
      <button class="confirm-btn" @click="submit">回答</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAssistant } from '../../composables/useAssistant'

const asst = useAssistant()
const answer = ref('')

const question = asst.pendingQuestion

function submit() {
  const v = answer.value.trim()
  if (!v) return
  asst.sendAnswer(v)
  answer.value = ''
}
</script>
```

`ChatInput.vue` 模板改为（用 `.chat-input-row` 包裹 textarea+发送按钮，卡片叠在行上方，不打乱横排）：
```vue
<template>
  <div class="chat-input">
    <QuestionCard v-if="asst.pendingQuestion.value" />
    <div class="chat-input-row">
      <textarea
        ref="ta"
        v-model="text"
        rows="1"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行"
        :disabled="disabled"
        @keydown.enter.exact.prevent="onEnter"
        @input="autosize"
      ></textarea>
      <button class="ci-send" :disabled="disabled || !text.trim()" @click="submit">
        <Icon name="send" :size="16" />
      </button>
    </div>
  </div>
</template>
```
`<script setup>` 顶部加：
```ts
import QuestionCard from './QuestionCard.vue'
import { useAssistant } from '../../composables/useAssistant'

const asst = useAssistant()
```
`<style scoped>` 中 `.chat-input` 改为纵向、子行保持横排：
```css
.chat-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 10px;
  border-top: 1px solid var(--border-base);
}
.chat-input-row { display: flex; align-items: flex-end; gap: 8px; }
```

`web/src/styles/assistant.css` 末尾追加共享样式：
```css
/* 澄清/确认问题回答卡片（悬浮球与控制台对话共用） */
.confirm-card { border: 1px solid #f59e0b; border-radius: 10px; background: rgba(245,158,11,.06); padding: 10px 12px; margin: 0 10px 8px; }
.confirm-title { font-size: 12px; font-weight: 600; color: #fbbf24; margin-bottom: 4px; }
.confirm-q { font-size: 13px; margin: 0 0 8px; color: var(--text-1); }
.confirm-row { display: flex; gap: 8px; }
.confirm-row input { flex: 1; background: #0b1120; border: 1px solid var(--border-base); border-radius: 8px; color: var(--text-1); padding: 6px 10px; font-size: 13px; }
.confirm-btn { background: none; border: 1px solid #f59e0b; color: #fbbf24; font-size: 12px; padding: 5px 14px; border-radius: 999px; cursor: pointer; }
```

- [ ] **Step 6: 前端构建验证**

Run: `cd web && npm run build`
Expected: 构建通过（vue-tsc 无类型错误）。

- [ ] **Step 7: Commit**

```bash
git add web/src
git commit -m "feat(前端): 对话切换到编排管线（streamUtter + 内联澄清问答卡片）"
```

---

### Task 5: 删除旧 ReAct 入口（#3 清理）

**Files:**
- Modify: `server.py`（删除 `/api/ai/chat`）
- Delete: `core/agent/legacy.py`、`core/agent.py`、`tests/test_agent.py`
- Modify: `core/agent/__init__.py`、`tests/test_server.py`
- Modify: `README.md`（API 端点表 / SSE 事件表 / 目录结构 / 测试说明）

**Interfaces:**
- Consumes: Task 3/4 完成后前端不再调 `/api/ai/chat`、`run_agent` 无引用。
- Produces: 工作区无 `run_agent`/`legacy`/`/api/ai/chat` 引用；`core.agent` 包仅剩 `base`/`coordinator`。

- [ ] **Step 1: 更新测试（`tests/test_server.py`）**

删除：
- 第 7 行 `from core import agent as agent_module`
- 整个「─── SSE 聊天 ───」小节（`test_ai_chat_unconfigured`、`test_ai_chat_sse_stream`，约 104-131 行）

- [ ] **Step 2: 删除后端旧入口**

`server.py` 删除 `/api/ai/chat` 端点（约 315-333 行）与其上方注释（第 151 行 `# ── /api/ai/chat：SSE 流式（ReAct + 工具）──`）。

删除文件：
```bash
rm -f core/agent/legacy.py core/agent.py tests/test_agent.py
```

`core/agent/__init__.py` 替换为：
```python
# -*- coding: utf-8 -*-
"""多智能体 — 子代理基座 / 协调者"""
from core.agent.base import SubAgentResult, run_subagent  # noqa: F401
from core.agent.coordinator import run_coordinator  # noqa: F401
```

- [ ] **Step 3: grep 确认无残留引用**

```bash
grep -rn "run_agent\|ai/chat\|legacy\|core.agent import" core/ server.py web/src tests/ --include=*.py --include=*.ts --include=*.vue 2>/dev/null | grep -v __pycache__
```
Expected: 无输出（`legacy` 关键字仅剩可能的注释，需人工确认无功能引用）。

- [ ] **Step 4: 同步 README**

`README.md`「API 端点」表删除 `POST /api/ai/chat` 一行。
「SSE 事件类型」段说明改为「`/api/voice/utter` 事件：…」并移除 `/api/ai/chat` 字样。
目录结构中 `core/agent/` 行改为 `│   ├── agent/                 base 子代理基座 + coordinator 多智能体协调者`（去掉 legacy 描述）。
「测试」段若提到 `/api/ai/chat` 一并清理。

- [ ] **Step 5: 全量验证**

Run: `python -m pytest tests/ -q`
Expected: 全部 PASS。
Run: `cd web && npm run build`
Expected: 构建通过。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: 删除旧 ReAct 入口（/api/ai/chat、legacy.py、agent.py）——编排管线为唯一 agent 路径"
```

---

## 执行顺序说明

Task 1（清理）与 Task 2（RAG）互相独立、无依赖，可任意先后。Task 3（后端增强）是 Task 4（前端切换）的前置；Task 5（删除旧入口）必须在 Task 4 之后（前端先切走、旧入口才可删）。每个 Task 结束保持可运行、可测试。
