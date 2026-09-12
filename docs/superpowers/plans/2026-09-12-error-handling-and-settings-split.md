# 后端静默失败点修复 + 前端错误处理统一与设置页拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `pipeline.py` 后台任务被 GC 导致长期记忆提取静默丢失的缺陷；引入统一的前端错误处理层（内联 `useAsync` + 全局 toast），并把 765 行的 `ConsoleSettings.vue` 拆成 8 个聚焦文件。

**Architecture:** 后端不动分层，仅在 `core/orchestrator/pipeline.py` 增加模块级后台任务引用集。前端新增一条错误处理基础设施（`errors.ts` / `useAsync` / `useToast` / `UiErrorNote` / `UiToaster`），console 域的 9 个组件从各自为政的 try/catch 迁移到该层；设置页按「元数据 / 状态 / 视图」三层拆分为 8 个文件，状态用模块级单例（与 `useConsole.ts`、`assistant/store.ts` 同模式）。

**Tech Stack:** Python 3.14 / FastAPI / pytest / mypy；Vue 3.4 + TypeScript + Vite 5 / vue-tsc / Vitest 4。

**Spec:** `docs/superpowers/specs/2026-09-12-error-handling-and-settings-split-design.md`

## Global Constraints

- Python 3.14+；后端沿用 `core/` 现有结构与**中英双语 docstring** 风格（`1d5e4db` 起全库双语，新增代码必须同样双语）。
- 前端注释同样中英双语（含 `<!-- -->` 模板注释与 `/** */` JSDoc）。
- 不改后端 API 契约与 `response_model`；`generated.ts` 无需重新生成（本次无 schema 变更）。
- 不引入新依赖：不装 `jsdom` / `@vue/test-utils`。
- 前端测试文件位置须匹配 `web/vitest.config.ts` 的 `include: ['src/**/*.spec.ts']`。
- 后端验证：`python -m pytest tests/ -q` + `python -m mypy core/ server.py`。
- 前端验证：`cd web && npm test` + `cd web && npm run build`。
- TDD：先写失败测试 → 运行确认失败 → 最小实现 → 运行确认通过 → 提交。
- **组件（`.vue`）改动无自动化测试覆盖**（无 jsdom），每个组件迁移后必须跑 `npm run build`，全部完成后人工跑页面比对。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `core/orchestrator/pipeline.py` | 编排管线；新增后台任务引用集 | Modify |
| `tests/test_orchestrator_pipeline.py` | 管线测试；新增 GC 回归用例 | Modify |
| `web/src/errors.ts` | `formatError` — 全站唯一错误文案来源 | Create |
| `web/src/composables/useAsync.ts` | 把 async 调用包成 `{data,error,loading,run}` | Create |
| `web/src/composables/useToast.ts` | 模块级单例通知队列 + `notify` | Create |
| `web/src/components/ui/UiErrorNote.vue` | 内联错误展示原语 | Create |
| `web/src/components/ui/UiToaster.vue` | toast 渲染容器（Teleport 到 body） | Create |
| `web/src/components/ui/index.ts` | UI 原语统一出口 | Modify |
| `web/src/App.vue` | 挂载 `<UiToaster />` | Modify |
| `web/src/components/console/settings/configDefs.ts` | 设置页配置元数据（纯数据，无 Vue） | Create |
| `web/src/components/console/settings/useSettings.ts` | 设置页状态单例 + 全部 API 操作 | Create |
| `web/src/components/console/settings/ServiceCard.vue` | LLM/ASR/TTS 服务卡 | Create |
| `web/src/components/console/settings/VoiceCard.vue` | 语音（唤醒 / VAD / TTS） | Create |
| `web/src/components/console/settings/AdvancedCard.vue` | 高级设置（5 子卡） | Create |
| `web/src/components/console/settings/VendorPicker.vue` | 厂商目录面板 | Create |
| `web/src/components/console/settings/ApiKeyModal.vue` | 密钥弹窗 | Create |
| `web/src/components/console/ConsoleSettings.vue` | 瘦身为编排壳（头 + 菜单 + 消息 + 组装） | Modify |
| `web/src/components/console/Console{Conversation,EnvView,History,MemoryView,ScheduleView,Status,TaskView,Tools}.vue` | 迁移到 `useAsync` / `notify` | Modify |

---

## Task 1: 后端后台任务持引用（2a）

**Files:**
- Modify: `core/orchestrator/pipeline.py`（顶部常量区 + `run_pipeline` 末尾）
- Test: `tests/test_orchestrator_pipeline.py`

**Interfaces:**
- Consumes: 无（本任务独立）
- Produces: `core.orchestrator.pipeline._bg_tasks: set[asyncio.Task]`、`core.orchestrator.pipeline._spawn_bg(coro) -> asyncio.Task` —— 供测试断言，其余任务不使用

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_orchestrator_pipeline.py` 末尾（文件已 `import asyncio` / `import pytest`，无需改 import 段）：

```python
@pytest.mark.asyncio
async def test_background_extract_task_is_referenced(monkeypatch):
    """后台记忆提取任务被持引用，且完成后自动移除（防 GC 导致静默丢失）。
    The background fact-extraction task is kept referenced and auto-discarded on
    completion (prevents silently losing it to GC).
    """
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session
    from core.orchestrator.task import Task

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_extract(task, result, store):
        started.set()
        await release.wait()

    async def fake_judge(text):
        return IntentResult(type="task", summary="测试任务")

    async def fake_form_task(intent):
        return Task(id="t1", goal="测试", params={}, missing=[], risk="read")

    async def fake_execute(task, session, token, events):
        return {"status": "done", "summary": "完成", "steps": []}

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "form_task", fake_form_task)
    monkeypatch.setattr(pl, "execute_task", fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", fake_extract)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    pl._bg_tasks.clear()
    session = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", session, events, StopController())
    await asyncio.wait_for(started.wait(), timeout=1)

    # 任务在飞行中被引用持有（旧实现无此集合 → AttributeError）
    assert len(pl._bg_tasks) == 1, "后台提取任务未被持引用，可能被 GC 回收"

    release.set()
    await asyncio.gather(*pl._bg_tasks)
    await asyncio.sleep(0)
    # 完成后 done_callback 已将其丢弃
    assert len(pl._bg_tasks) == 0, "已完成的后台任务未被清理，引用集会持续增长"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_orchestrator_pipeline.py::test_background_extract_task_is_referenced -v`
Expected: FAIL — `AttributeError: module 'core.orchestrator.pipeline' has no attribute '_bg_tasks'`（或 `monkeypatch.setattr` 报属性不存在）

- [ ] **Step 3: 实现**

在 `core/orchestrator/pipeline.py` 的 `EventQueueChannel` 类定义**之前**（`import` 段之后）插入：

```python
# 后台任务引用集：CPython 的事件循环对 Task 仅持弱引用，不保留句柄的任务
# 可能在执行完成前被垃圾回收 —— 而 extract_and_store 内部吞掉所有异常
# （core/memory/extract.py），后果是长期记忆提取静默不发生、无任何报错痕迹。
#
# Background-task reference set: CPython's event loop only holds weak references
# to Tasks, so a task without a retained handle may be garbage-collected before it
# finishes — and extract_and_store swallows all exceptions internally
# (core/memory/extract.py), making the consequence a silent loss of long-term
# fact extraction with no error trace.
_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg(coro) -> asyncio.Task:
    """启动后台任务并持有引用，完成后自动丢弃。

    Start a background task while holding a reference, discarding it on completion.

    Args:
        coro: 要调度的协程。The coroutine to schedule.

    Returns:
        已调度的 Task。The scheduled Task.
    """
    t = asyncio.ensure_future(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)
    return t
```

再把 `run_pipeline` 末尾（约 `pipeline.py:148`）的这一行：

```python
        asyncio.ensure_future(extract_and_store(task, result, get_facts_store()))
```

替换为：

```python
        _spawn_bg(extract_and_store(task, result, get_facts_store()))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_orchestrator_pipeline.py -v`
Expected: PASS（含新增用例在内的全部管线测试）

- [ ] **Step 5: 全量后端回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过；mypy `Success: no issues found in 80 source files`

- [ ] **Step 6: 提交**

```bash
git add core/orchestrator/pipeline.py tests/test_orchestrator_pipeline.py
git commit -m "fix(编排): 后台记忆提取任务持引用 — 防止被 GC 导致静默丢失

asyncio 仅对 Task 持弱引用，pipeline 的 extract_and_store 未保留句柄，
可能在完成前被回收；该函数内部吞掉所有异常，故失败无任何痕迹。
新增模块级 _bg_tasks 集合 + _spawn_bg()，并补 GC 回归测试。"
```

---

## Task 2: 前端错误处理基础设施（3b）

**Files:**
- Create: `web/src/errors.ts`, `web/src/composables/useAsync.ts`, `web/src/composables/useToast.ts`, `web/src/components/ui/UiErrorNote.vue`, `web/src/components/ui/UiToaster.vue`
- Modify: `web/src/components/ui/index.ts`, `web/src/App.vue`
- Test: `web/src/errors.spec.ts`, `web/src/composables/useAsync.spec.ts`, `web/src/composables/useToast.spec.ts`

**Interfaces:**
- Consumes: 无
- Produces:
  - `formatError(e: unknown): string`
  - `useAsync<T>(fn: (...args: any[]) => Promise<T>): { data: Ref<T|null>; error: Ref<string|null>; loading: Ref<boolean>; run: (...args: any[]) => Promise<T|null> }`
  - `notify: { ok(text): void; err(text): void; warn(text): void; info(text): void; dismiss(id: number): void; clear(): void }`、`useToast(): { items: Ref<ToastItem[]> }`、`ToastKind`、`ToastItem`
  - 组件 `UiErrorNote`（props: `error: string | null | undefined`）、`UiToaster`

- [ ] **Step 1: 写三个失败测试**

创建 `web/src/errors.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { formatError } from './errors'

/** formatError 的单元测试。Unit tests for formatError. */
describe('formatError', () => {
  it('提取 Error 的 message', () => {
    expect(formatError(new Error('连接超时'))).toBe('连接超时')
  })

  it('字符串原样返回', () => {
    expect(formatError('后端拒绝')).toBe('后端拒绝')
  })

  it('空值回退为未知错误', () => {
    expect(formatError(undefined)).toBe('未知错误')
    expect(formatError(null)).toBe('未知错误')
    expect(formatError('')).toBe('未知错误')
  })

  it('任意对象转为字符串', () => {
    expect(formatError({ code: 500 })).toBe('[object Object]')
  })
})
```

创建 `web/src/composables/useAsync.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { useAsync } from './useAsync'

/** useAsync 的单元测试。Unit tests for useAsync. */
describe('useAsync', () => {
  it('成功时写入 data 并复位 loading', async () => {
    const { data, error, loading, run } = useAsync(async () => 42)
    const p = run()
    expect(loading.value).toBe(true)
    expect(await p).toBe(42)
    expect(data.value).toBe(42)
    expect(error.value).toBeNull()
    expect(loading.value).toBe(false)
  })

  it('失败时写入 error 且 data 保持为 null', async () => {
    const { data, error, loading, run } = useAsync(async () => {
      throw new Error('拉取失败')
    })
    expect(await run()).toBeNull()
    expect(error.value).toBe('拉取失败')
    expect(data.value).toBeNull()
    expect(loading.value).toBe(false)
  })

  it('再次 run 会先清空上一次的 error', async () => {
    let shouldFail = true
    const { data, error, run } = useAsync(async () => {
      if (shouldFail) throw new Error('第一次失败')
      return 'ok'
    })
    await run()
    expect(error.value).toBe('第一次失败')
    shouldFail = false
    await run()
    expect(error.value).toBeNull()
    expect(data.value).toBe('ok')
  })

  it('透传参数给被包装函数', async () => {
    const { data, run } = useAsync(async (a: number, b: number) => a + b)
    await run(2, 3)
    expect(data.value).toBe(5)
  })
})
```

创建 `web/src/composables/useToast.spec.ts`：

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { notify, useToast } from './useToast'

/** useToast 的单元测试。Unit tests for useToast. */
describe('useToast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    notify.clear()
  })
  afterEach(() => {
    notify.clear()
    vi.useRealTimers()
  })

  it('入队后出现在 items 中并带类型', () => {
    const { items } = useToast()
    notify.ok('已保存')
    expect(items.value).toHaveLength(1)
    expect(items.value[0].kind).toBe('ok')
    expect(items.value[0].text).toBe('已保存')
  })

  it('到达存活时长后自动消失', () => {
    const { items } = useToast()
    notify.err('保存失败')
    expect(items.value).toHaveLength(1)
    vi.advanceTimersByTime(4000)
    expect(items.value).toHaveLength(0)
  })

  it('错误类型存活更久（6000ms）', () => {
    const { items } = useToast()
    notify.err('保存失败')
    vi.advanceTimersByTime(4000)
    expect(items.value).toHaveLength(1)
    vi.advanceTimersByTime(2000)
    expect(items.value).toHaveLength(0)
  })

  it('dismiss 立即移除指定条目', () => {
    const { items } = useToast()
    notify.info('提示')
    const id = items.value[0].id
    notify.dismiss(id)
    expect(items.value).toHaveLength(0)
  })

  it('多条并存，各自独立计时', () => {
    const { items } = useToast()
    notify.ok('a')
    notify.ok('b')
    expect(items.value).toHaveLength(2)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web && npx vitest run src/errors.spec.ts src/composables/useAsync.spec.ts src/composables/useToast.spec.ts`
Expected: FAIL — `Failed to resolve import "./errors"` / `"./useAsync"` / `"./useToast"`

- [ ] **Step 3: 实现 `web/src/errors.ts`**

```ts
/**
 * 错误文案统一入口：全站唯一的错误 → 字符串转换点。
 * Central error-message entry: the single error-to-string conversion point.
 */

/**
 * 把任意异常转成可展示的错误文案。
 * Convert any thrown value into a displayable error message.
 *
 * @param e 捕获到的异常。The caught exception.
 * @returns 错误文案；空值回退为「未知错误」。The message, falling back to a generic one for empty values.
 */
export function formatError(e: unknown): string {
  if (e instanceof Error) return e.message || '未知错误'
  if (typeof e === 'string') return e.trim() || '未知错误'
  if (e === null || e === undefined) return '未知错误'
  return String(e)
}
```

- [ ] **Step 4: 实现 `web/src/composables/useAsync.ts`**

```ts
import { ref, type Ref } from 'vue'
import { formatError } from '../errors'

/**
 * useAsync 的返回结构。The shape returned by useAsync.
 */
export interface UseAsyncResult<T> {
  /** 最近一次成功的结果。The most recent successful result. */
  data: Ref<T | null>
  /** 最近一次失败的错误文案（成功时清空）。The last failure message (cleared on success). */
  error: Ref<string | null>
  /** 是否正在执行。Whether a call is in flight. */
  loading: Ref<boolean>
  /** 触发调用；失败不抛出，错误写入 error。Trigger the call; failures are captured, not thrown. */
  run: (...args: any[]) => Promise<T | null>
}

/**
 * 把一次异步调用包成 { data, error, loading, run }，统一错误捕获与文案格式化。
 * Wrap an async call into { data, error, loading, run } with unified error capture
 * and message formatting.
 *
 * @param fn 被包装的异步函数。The async function to wrap.
 * @returns 响应式状态与触发函数。Reactive state and the trigger function.
 */
export function useAsync<T>(fn: (...args: any[]) => Promise<T>): UseAsyncResult<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref<string | null>(null)
  const loading = ref(false)

  async function run(...args: any[]): Promise<T | null> {
    loading.value = true
    error.value = null
    try {
      const r = await fn(...args)
      data.value = r
      return r
    } catch (e) {
      error.value = formatError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  return { data, error, loading, run }
}
```

- [ ] **Step 5: 实现 `web/src/composables/useToast.ts`**

```ts
import { ref, type Ref } from 'vue'

/** 通知类型。Notification kind. */
export type ToastKind = 'ok' | 'err' | 'warn' | 'info'

/** 单条通知。A single notification entry. */
export interface ToastItem {
  /** 自增 id，用于 dismiss。Auto-increment id, used for dismiss. */
  id: number
  /** 通知类型（决定色调与存活时长）。Kind (drives tone and lifetime). */
  kind: ToastKind
  /** 通知文案。Notification text. */
  text: string
}

/** 各类型的存活时长（ms）；错误留更久以便阅读。Per-kind lifetime in ms; errors linger longer. */
const TTL: Record<ToastKind, number> = { ok: 3500, info: 3500, warn: 5000, err: 6000 }

/** 模块级单例队列：任意组件调用 notify 都会写进同一份列表。
 *  Module-level singleton queue: notify from any component writes into one list. */
const items = ref<ToastItem[]>([])
let seq = 0

/**
 * 入队一条通知并安排自动移除。
 * Enqueue a notification and schedule its auto-removal.
 */
function push(kind: ToastKind, text: string): void {
  const id = ++seq
  items.value = [...items.value, { id, kind, text }]
  setTimeout(() => dismiss(id), TTL[kind])
}

/**
 * 立即移除指定通知。
 * Remove a notification immediately.
 *
 * @param id 通知 id。The notification id.
 */
function dismiss(id: number): void {
  items.value = items.value.filter((t) => t.id !== id)
}

/** 全局通知入口。Global notification entry point. */
export const notify = {
  /** 成功提示。Success notice. */
  ok: (text: string) => push('ok', text),
  /** 错误提示。Error notice. */
  err: (text: string) => push('err', text),
  /** 警告提示。Warning notice. */
  warn: (text: string) => push('warn', text),
  /** 普通信息。Informational notice. */
  info: (text: string) => push('info', text),
  /** 立即移除某条。Dismiss one entry. */
  dismiss,
  /** 清空全部（测试用）。Clear all (for tests). */
  clear: () => {
    items.value = []
  },
}

/**
 * 读取通知队列（供 UiToaster 渲染）。
 * Read the notification queue (rendered by UiToaster).
 *
 * @returns 通知列表。The notification list.
 */
export function useToast(): { items: Ref<ToastItem[]> } {
  return { items }
}
```

- [ ] **Step 6: 运行三个测试确认通过**

Run: `cd web && npx vitest run src/errors.spec.ts src/composables/useAsync.spec.ts src/composables/useToast.spec.ts`
Expected: PASS（全部用例）

- [ ] **Step 7: 实现两个 UI 原语**

创建 `web/src/components/ui/UiErrorNote.vue`：

```vue
<template>
  <!-- 内联错误提示：统一的加载失败展示样式。Inline error note: unified load-failure display. -->
  <div v-if="error" class="ui-errnote">{{ error }}</div>
</template>

<script setup lang="ts">
/** 组件 props：错误文案（空则不渲染）。Component props: error text (nothing renders when empty). */
defineProps<{ error: string | null | undefined }>()
</script>

<style scoped>
.ui-errnote {
  font-size: var(--fs-xs); color: #f87171;
  background: rgba(248, 113, 113, .07); border: 1px solid rgba(248, 113, 113, .3);
  border-radius: var(--r-sm); padding: 7px 10px;
}
</style>
```

创建 `web/src/components/ui/UiToaster.vue`：

```vue
<template>
  <!-- 通知浮层：Teleport 到 body，不参与页面布局。Notification overlay: teleported to body, outside page layout. -->
  <Teleport to="body">
    <div v-if="items.length" class="ui-toaster">
      <div
        v-for="t in items"
        :key="t.id"
        class="ui-toast"
        :class="'k-' + t.kind"
        @click="notify.dismiss(t.id)"
      >
        {{ t.text }}
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { notify, useToast } from '../../composables/useToast'

/** 通知队列（模块级单例）。The notification queue (module-level singleton). */
const { items } = useToast()
</script>

<style scoped>
.ui-toaster {
  position: fixed; right: 18px; bottom: 18px; z-index: 3000;
  display: flex; flex-direction: column; gap: 8px; align-items: flex-end;
  pointer-events: none;
}
.ui-toast {
  font-size: var(--fs-xs); max-width: 420px; cursor: pointer;
  border-radius: var(--r-sm); padding: 8px 12px;
  border: 1px solid var(--border-soft); background: rgba(11, 17, 32, .96);
  color: var(--text-1); pointer-events: auto;
  box-shadow: 0 6px 20px rgba(0, 0, 0, .45);
  animation: ui-toast-in .18s ease-out;
}
.ui-toast.k-ok { color: #34d399; border-color: rgba(52, 211, 153, .4); }
.ui-toast.k-err { color: #f87171; border-color: rgba(248, 113, 113, .4); }
.ui-toast.k-warn { color: #fbbf24; border-color: rgba(251, 191, 36, .4); }
.ui-toast.k-info { color: var(--text-2); }

@keyframes ui-toast-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
```

- [ ] **Step 8: 导出原语并挂载**

在 `web/src/components/ui/index.ts` 末尾追加：

```ts
export { default as UiErrorNote } from './UiErrorNote.vue'
export { default as UiToaster } from './UiToaster.vue'
```

在 `web/src/App.vue` 中：import 段加入

```ts
import { UiToaster } from './components/ui'
```

模板中在 `<FloatingAssistant :asst="asst" />` **之后**加入：

```vue
  <!-- 全局通知浮层（错误 / 成功提示） -->
  <!-- Global notification overlay (error / success notices) -->
  <UiToaster />
```

- [ ] **Step 9: 类型检查与全量前端回归**

Run: `cd web && npm test && npm run build`
Expected: Vitest 全部通过（原 7 例 + 新增 13 例）；`vue-tsc` 无错误；vite 构建成功

- [ ] **Step 10: 提交**

```bash
git add web/src/errors.ts web/src/errors.spec.ts web/src/composables/useAsync.ts web/src/composables/useAsync.spec.ts web/src/composables/useToast.ts web/src/composables/useToast.spec.ts web/src/components/ui/UiErrorNote.vue web/src/components/ui/UiToaster.vue web/src/components/ui/index.ts web/src/App.vue
git commit -m "feat(web): 统一错误处理基础设施 — formatError / useAsync / useToast

- errors.ts: 全站唯一错误文案转换点
- useAsync: 把异步调用包成 {data,error,loading,run}，统一捕获
- useToast + UiToaster + UiErrorNote: 操作反馈走全局浮层，加载错误内联展示
- 三个新模块均有 Vitest 覆盖（纯逻辑，沿用现有 node 测试环境）"
```

---

## Task 3: 设置页元数据与状态单例（3a 上半）

**Files:**
- Create: `web/src/components/console/settings/configDefs.ts`, `web/src/components/console/settings/useSettings.ts`
- Modify: 无（本任务只新增，不接线的部分在 Task 4）
- Test: 无自动化测试（纯搬运 + 逻辑，`.vue` 之外的类型由 Task 4 的 `npm run build` 覆盖）

**Interfaces:**
- Consumes: Task 2 的 `formatError`、`notify`
- Produces:
  - `configDefs.ts`: `menuDefs`、`sectionDefs`、`advancedDefs`、`NUMERIC`、`LABELS`、`fieldLabel(f: string): string`、`isNumericField(f: string): boolean`、类型 `MenuDef` / `SectionDef` / `AdvancedDef`
  - `useSettings.ts`: `useSettings()` 返回 `{ app, editable, saving, detecting, connResults, issues, catalog, addingSection, customAdding, customName, activeMenu, keyModal, showKey, sec, ed, menuDot, activeProfile, vendorPreset, vendorList, modelOptions, voiceOptions, presetToProfile, toggleAdding, confirmCustom, addProfileFromVendor, deleteProfile, fetchModelsFor, saveModule, load, detectAll, detectOne, openKeyModal, keyEnvHint, confirmKey, clearKey, loadCatalog }`

> **搬运原则**：本任务从 `ConsoleSettings.vue` 原样搬运代码块，**除下列三处改动外逐字保留**：
> 1. `msg` / `restartHint` 两个 ref **删除**，对应赋值改为 `notify` 调用；
> 2. `isErr()` **删除**（字符串嗅探，由 toast 类型取代）；
> 3. 所有错误文案的半角冒号 `'X失败: '` 统一为全角 `'X失败：'`，并把拼接的 `(e?.message || '')` 换成 `formatError(e)`。

- [ ] **Step 1: 创建 `configDefs.ts`**

从 `ConsoleSettings.vue` 搬运 `menuDefs`(258–264)、`sectionDefs`(267–274)、`advancedDefs`(277–288)、`NUMERIC`(291–294)、`LABELS`(297–306)、`fieldLabel`(317–319)、`num`(321–323)，加上类型与双语注释：

```ts
/**
 * 设置页配置元数据：模块 / 字段 / 标签的单一来源，无 Vue 依赖。
 * Settings-page config metadata: the single source of truth for modules, fields
 * and labels. No Vue dependency.
 */

/** 左侧菜单项定义。Left menu item definition. */
export interface MenuDef {
  /** 模块 id（同时是 editable 快照上的 key）。Module id (also the key on the editable snapshot). */
  id: string
  /** 菜单显示名。Menu label. */
  label: string
  /** 图标名。Icon name. */
  icon: string
}

/** 服务模块（LLM / ASR / TTS）定义。Service module (LLM / ASR / TTS) definition. */
export interface SectionDef {
  /** editable 快照上的 key。Key on the editable snapshot. */
  key: string
  /** 连通性结果名（对应 /api/detection）。Connectivity result name (from /api/detection). */
  name: string
  /** 卡片标题。Card title. */
  title: string
  /** 是否有启用开关。Whether an enable toggle is shown. */
  toggle: boolean
  /** 可编辑字段名列表。Editable field names. */
  fields: string[]
}

/** 高级设置子卡定义。Advanced sub-card definition. */
export interface AdvancedDef {
  /** editable 快照上的 key。Key on the editable snapshot. */
  key: string
  /** 子卡标题。Sub-card title. */
  title: string
  /** [字段名, 控件类型] 列表。List of [field name, control type]. */
  fields: readonly (readonly [string, 'number' | 'bool' | 'text'])[]
}

/** 左侧菜单定义。Left menu definitions. */
export const menuDefs: MenuDef[] = [
  { id: 'llm', label: '大模型', icon: 'brain' },
  { id: 'asr', label: '语音识别', icon: 'mic' },
  { id: 'tts', label: '语音合成', icon: 'volume' },
  { id: 'voice', label: '语音唤醒', icon: 'ear' },
  { id: 'advanced', label: '高级设置', icon: 'zap' },
]

/** 三大服务 section 定义（name 对应 /api/detection 的连通性结果名）。Three service section definitions (name matches the /api/detection connectivity result name). */
export const sectionDefs: SectionDef[] = [
  { key: 'llm', name: 'LLM', title: 'LLM 大模型', toggle: false,
    fields: ['provider', 'endpoint', 'model', 'chat_path', 'max_tokens', 'temperature', 'timeout'] },
  { key: 'asr', name: 'ASR', title: 'ASR 语音识别', toggle: false,
    fields: ['provider', 'endpoint', 'model', 'language', 'chat_path', 'timeout'] },
  { key: 'tts', name: 'TTS', title: 'TTS 语音合成', toggle: true,
    fields: ['provider', 'endpoint', 'model', 'voice', 'format', 'chat_path', 'timeout'] },
]

/** 高级模块定义（Agent / LLM 客户端 / 工具 / RAG / 服务器）。Advanced module definitions (Agent / LLM client / Tools / RAG / Server). */
export const advancedDefs: AdvancedDef[] = [
  { key: 'agent', title: 'Agent 任务执行',
    fields: [['recursion_limit', 'number'], ['multi_agent', 'bool'], ['structured_temperature', 'number']] },
  { key: 'llm_client', title: 'LLM 客户端（重试 / 熔断）',
    fields: [['retry_max', 'number'], ['retry_backoff_base', 'number'], ['retry_backoff_max', 'number'],
      ['circuit_breaker_threshold', 'number'], ['circuit_breaker_cooldown', 'number'], ['request_timeout', 'number']] },
  { key: 'tools', title: '工具参数',
    fields: [['search_max_results', 'number'], ['weather_timeout', 'number']] },
  { key: 'rag', title: 'RAG 检索', fields: [['auto_index', 'bool']] },
  { key: 'server', title: '服务器',
    fields: [['host', 'text'], ['port', 'number'], ['open_browser', 'bool']] },
]

/** 需要数值类型的字段集合。Set of fields that require numeric input. */
export const NUMERIC = new Set([
  'max_tokens', 'temperature', 'timeout', 'sensitivity', 'silence_threshold',
  'silence_duration_ms', 'max_duration_ms', 'recursion_limit', 'structured_temperature', 'retry_max',
  'retry_backoff_base', 'retry_backoff_max', 'circuit_breaker_threshold', 'circuit_breaker_cooldown',
  'request_timeout', 'search_max_results', 'weather_timeout', 'port',
])

/** 字段中文标签映射。Chinese label mapping for fields. */
export const LABELS: Record<string, string> = {
  provider: '协议', endpoint: 'Endpoint', model: '模型', vision_model: '视觉模型',
  chat_path: 'Chat Path', max_tokens: 'Max Tokens', temperature: 'Temperature', timeout: '超时(s)',
  language: '语言', voice: '音色', format: '格式', recursion_limit: 'ReAct 步数上限',
  multi_agent: '多智能体', structured_temperature: '结构化输出温度', retry_max: '重试次数',
  retry_backoff_base: '退避基数(s)', retry_backoff_max: '退避上限(s)', circuit_breaker_threshold: '熔断阈值',
  circuit_breaker_cooldown: '熔断冷却(s)',
  request_timeout: '请求超时(s)', search_max_results: '搜索结果数', weather_timeout: '天气超时(s)',
  auto_index: '自动建索引', host: 'Host', port: 'Port', open_browser: '启动打开浏览器',
}

/**
 * 根据字段名获取中文标签。
 * Get the Chinese label for a field name.
 *
 * @param f 字段名。Field name.
 * @returns 标签，缺省回退为字段名本身。The label, falling back to the field name itself.
 */
export function fieldLabel(f: string): string {
  return LABELS[f] || f
}

/**
 * 判断字段是否应使用数值输入。
 * Check whether a field should use numeric input.
 *
 * @param f 字段名。Field name.
 * @returns 是否为数值字段。Whether the field is numeric.
 */
export function isNumericField(f: string): boolean {
  return NUMERIC.has(f)
}
```

- [ ] **Step 2: 创建 `useSettings.ts`**

模块级单例 state + 搬运全部操作函数。**注意 `advancedDefs` 的 `fields` 用 `readonly` 元组后，Step 1 里 `advancedDefs` 的 `as const` 已不需要 —— 直接按上面的定义，`AdvancedDef.fields` 类型即接受。**

```ts
import { ref } from 'vue'
import { api } from '../../api'
import { useConfig } from '../../../composables/useApi'
import { notify } from '../../../composables/useToast'
import { formatError } from '../../../errors'
import type {
  ConnectivityResult, DetectionIssue, EditableSnapshot, ProfileConfig, ProviderPreset,
} from '../../../types'

/**
 * 设置页状态单例 + API 操作。
 * Settings-page state singleton + API operations.
 *
 * state 定义在模块顶层（与 useConsole.ts 的 activeTab、assistant/store.ts 同模式），
 * 因此各子组件无需逐层传 props 即可共享同一份配置快照。副作用：state 跨
 * ConsoleSettings 挂载/卸载存活，故必须保留 onMounted 时重新 load() 的行为。
 *
 * State lives at module top level (same pattern as useConsole.ts's activeTab and
 * assistant/store.ts), so sub-components share one config snapshot without prop
 * drilling. Side effect: state survives ConsoleSettings mount/unmount, so the
 * onMounted re-load() behaviour MUST be preserved.
 */

/** 全局配置缓存（tts_available、当前 profile 等）。Global config cache (tts_available, current profile, etc.). */
const app = useConfig()
/** 可编辑配置快照（从后端 /api/config/full 获取）。Editable config snapshot (from backend /api/config/full). */
const editable = ref<EditableSnapshot | null>(null)
/** 保存中状态标志。Saving state flag. */
const saving = ref(false)
/** 检测中状态标志。Detection in progress flag. */
const detecting = ref(false)
/** 连通性检测结果（按服务名索引）。Connectivity results (indexed by service name). */
const connResults = ref<Record<string, ConnectivityResult>>({})
/** 配置校验问题列表。Config validation issues. */
const issues = ref<DetectionIssue[]>([])
/** 厂商目录预设列表（按模块分组）。Vendor catalog presets (grouped by module). */
const catalog = ref<Record<string, ProviderPreset[]> | null>(null)
/** 当前正在新增 Profile 的模块 key。Module key currently adding a Profile. */
const addingSection = ref<string | null>(null)
/** 是否正在输入自定义 Profile 名称。Whether custom Profile name input is active. */
const customAdding = ref<string | null>(null)
/** 自定义 Profile 名称。Custom Profile name. */
const customName = ref('')
/** 左侧菜单当前选中项。Currently selected left menu item. */
const activeMenu = ref('llm')
/** 密钥弹出框状态（section / profile / value）。API Key modal state. */
const keyModal = ref<{ section: string; profile: string; value: string } | null>(null)
/** 是否显示明文密钥。Whether to show the key in plain text. */
const showKey = ref(false)

/** 获取指定模块的可编辑配置对象。Get the editable config object for a module. */
function sec(key: string): any {
  return (editable.value as any)?.[key]
}
/** 语音模块顶层对象（wake_word / vad 直接挂在 editable 根）。Voice module top-level object (wake_word / vad sit at the editable root). */
function ed(): any {
  return editable.value
}

/** 判断指定菜单项是否显示绿点（密钥已设置）。Check whether a menu item shows the "key set" dot. */
function menuDot(id: string): boolean {
  if (id === 'llm' || id === 'asr' || id === 'tts') {
    const s = (editable.value as any)?.[id]
    return !!s?.api_key_set?.[s.active]
  }
  return false
}

/** 获取当前活跃的 Profile 配置。Get the currently active Profile config. */
function activeProfile(s: any): ProfileConfig {
  return (editable.value as any)?.[s.key]?.profiles?.[(editable.value as any)[s.key].active] || {}
}
/** 根据 Profile 的 vendor 字段查找对应的厂商预设。Find the vendor preset matching the Profile's vendor field. */
function vendorPreset(s: any): ProviderPreset | null {
  const prof = activeProfile(s)
  if (!prof.vendor || !catalog.value) return null
  return catalog.value[s.key]?.find((v) => v.id === prof.vendor) || null
}
/** 获取指定模块的厂商预设列表。Get the vendor preset list for a module. */
function vendorList(key: string): ProviderPreset[] {
  return (catalog.value && catalog.value[key]) || []
}
/** 合并 Profile 和厂商预设的模型列表（去重）。Merge model lists from Profile and vendor preset (deduplicated). */
function modelOptions(s: any): string[] {
  const prof = activeProfile(s)
  const v = vendorPreset(s)
  return [...new Set([...(prof.models || []), ...(v?.models || [])])].filter(Boolean)
}
/** 合并 Profile 和厂商预设的音色列表（去重）。Merge voice lists from Profile and vendor preset (deduplicated). */
function voiceOptions(s: any): string[] {
  const prof = activeProfile(s)
  const v = vendorPreset(s)
  return [...new Set([...(prof.voices || []), ...(v?.voices || [])])].filter(Boolean)
}
/** 目录预设 → 可编辑 profile（与后端 core/providers.preset_to_profile 对齐）。Convert a catalog preset to an editable profile (aligned with the backend's core/providers.preset_to_profile). */
function presetToProfile(v: ProviderPreset): ProfileConfig {
  const p: any = {
    provider: v.provider || 'openai',
    vendor: v.id,
    endpoint: v.endpoint,
    chat_path: v.chat_path || '/v1/chat/completions',
    models: [...v.models],
    model: v.defaults?.model || v.models[0] || '',
    api_key_env: v.api_key_env,
    compat: { ...v.compat },
  }
  if (v.models_path) p.models_path = v.models_path
  if (v.vision_models?.length) p.vision_model = v.vision_models[0]
  if (v.voices?.length) {
    p.voices = [...v.voices]
    p.voice = v.defaults?.voice || v.voices[0]
  }
  for (const [k, val] of Object.entries(v.defaults || {})) {
    if (p[k] === undefined) p[k] = val
  }
  return p
}

/** 切换「新增 Profile」面板的展开/折叠。Toggle the "Add Profile" panel. */
function toggleAdding(key: string) {
  addingSection.value = addingSection.value === key ? null : key
  customAdding.value = null
}

/** 按模块产出 PATCH body（service: 只该 section；voice: 唤醒+VAD；advanced: 全部高级段）。Build the PATCH body by module. */
function moduleBody(id: string): Record<string, any> {
  const e = editable.value as any
  if (id === 'voice') return { wake_word: e.wake_word, vad: e.vad }
  if (id === 'advanced') {
    return {
      agent: e.agent,
      llm_client: e.llm_client,
      tools: e.tools,
      rag: e.rag,
      server: { host: e.server.host, port: e.server.port, open_browser: e.server.open_browser, cors_origins: e.server.cors_origins },
      mcp: e.mcp,
    }
  }
  if (id === 'tts') return { tts: { enabled: e.tts.enabled, active: e.tts.active, profiles: e.tts.profiles } }
  return { [id]: { active: e[id].active, profiles: e[id].profiles } }
}

/** 只持久化单个模块（新增/删除 Profile 用，静默不弹提示）。Persist a single module only (for add/delete Profile, silently). */
async function persistSection(key: string): Promise<boolean> {
  if (!editable.value) return false
  try {
    const r = await api.patchConfig(moduleBody(key))
    return !!r.ok
  } catch {
    return false
  }
}

/** 自定义空白 Profile：内联输入取名 → 建空 profile 并立即保存。Custom blank Profile: inline name input, created and saved immediately. */
async function confirmCustom(key: string) {
  const name = customName.value.trim() || 'custom'
  const profiles = (editable.value as any)[key].profiles
  if (profiles[name]) { notify.err(`Profile「${name}」已存在`); return }
  profiles[name] = { provider: 'openai', chat_path: '/v1/chat/completions', models: [] }
  ;(editable.value as any)[key].active = name
  customAdding.value = null
  customName.value = ''
  const ok = await persistSection(key)
  if (ok) notify.ok(`已添加并保存空白 Profile「${name}」，请填写 endpoint/模型 并设置 API Key`)
  else notify.err(`已添加 Profile「${name}」（保存失败，请检查后手动保存）`)
}

/** 从厂商目录新增 Profile 并立即保存。Add a Profile from the vendor catalog and save immediately. */
async function addProfileFromVendor(key: string, v: ProviderPreset) {
  const profiles = (editable.value as any)[key].profiles
  let name = v.id
  let i = 2
  while (profiles[name]) name = `${v.id}-${i++}`
  profiles[name] = presetToProfile(v)
  ;(editable.value as any)[key].active = name
  addingSection.value = null
  const ok = await persistSection(key)
  if (ok) notify.ok(`已添加并保存 Profile「${name}」，请设置 API Key`)
  else notify.err(`已添加 Profile「${name}」（保存失败，请检查后手动保存）`)
}

/** 删除指定 Profile（至少保留一个）。Delete a Profile (at least one must remain). */
async function deleteProfile(key: string) {
  const s = (editable.value as any)[key]
  const names = Object.keys(s.profiles)
  if (names.length <= 1) { notify.err('至少保留一个 Profile'); return }
  const name = s.active
  if (!window.confirm(`删除 Profile「${name}」？`)) return
  delete s.profiles[name]
  const rest = Object.keys(s.profiles)
  if (!rest.includes(s.active)) s.active = rest[0]
  const ok = await persistSection(key)
  if (ok) notify.ok(`已删除 Profile「${name}」`)
  else notify.err(`已删除 Profile「${name}」（保存失败，请检查）`)
}

/** 拉取当前 profile 的模型列表（openai/anthropic/gemini 均支持），写回 profile.models。Fetch the model list for the current profile and write it back to profile.models. */
async function fetchModelsFor(s: any) {
  const prof = activeProfile(s)
  const profile = { name: (editable.value as any)[s.key].active, ...prof }
  try {
    const r = await api.fetchModels(s.key, profile)
    if (r.ok) {
      prof.models = r.models
      if (r.models.length && (!prof.model || !r.models.includes(prof.model))) prof.model = r.models[0]
      notify.ok(`已获取 ${r.count} 个模型`)
    } else {
      notify.err('获取模型失败：' + (r.error || ''))
    }
  } catch (e) {
    notify.err('获取模型失败：' + formatError(e))
  }
}

/** 保存单个模块的配置到后端。Save a single module's config to the backend. */
async function saveModule(id: string) {
  if (!editable.value) return
  saving.value = true
  try {
    const r = await api.patchConfig(moduleBody(id))
    if (r.ok) {
      notify.ok(r.restart_required ? '已保存（部分设置重启后生效）' : '已保存（已即时生效）')
      if (r.restart_required) notify.warn('服务器绑定 / MCP 已变更，重启服务后生效')
      // 刷新全局 /api/config 缓存，让 tts_available / 当前 profile 等即时更新（无需刷新页面）
      // Refresh the global /api/config cache so tts_available / current profile update immediately.
      app.refreshConfig()
    } else {
      notify.err('保存失败：' + (r.error || ''))
    }
  } catch (e) {
    notify.err('保存失败：' + formatError(e))
  } finally {
    saving.value = false
  }
}

/** 从后端加载完整可编辑配置。Load the full editable config from the backend. */
async function load() {
  try {
    const r = await api.getConfigFull()
    if (r.ok && r.editable) {
      editable.value = r.editable
      // 若当前 active profile 不在 profiles（可能被清），回退到第一个
      // If the active profile is missing from profiles, fall back to the first one.
      for (const key of ['llm', 'asr', 'tts'] as const) {
        const s: any = r.editable[key]
        if (s && !s.profiles[s.active] && Object.keys(s.profiles).length) {
          s.active = Object.keys(s.profiles)[0]
        }
      }
    } else {
      notify.err('加载配置失败')
    }
  } catch (e) {
    notify.err('加载配置失败：' + formatError(e))
  }
}

/** 检测全部服务连通性。Test connectivity for all services. */
async function detectAll() {
  detecting.value = true
  issues.value = []
  try {
    const r = await api.getDetection()
    if (r.ok && r.report) {
      connResults.value = Object.fromEntries(r.report.connectivity.map((c) => [c.name, c]))
      issues.value = r.report.config.issues
    } else {
      notify.err('检测失败：' + ((r as any)?.error || ''))
    }
  } catch (e) {
    notify.err('检测失败：' + formatError(e))
  } finally {
    detecting.value = false
  }
}

/** 检测单个服务连通性。Test connectivity for a single service. */
async function detectOne(name: string) {
  detecting.value = true
  try {
    const r = await api.getDetection()
    if (r.ok) {
      const c = r.report.connectivity.find((x) => x.name === name)
      if (c) connResults.value = { ...connResults.value, [name]: c }
    }
  } catch {
    /* 静默：单服务检测失败不影响整体显示 / Silent: a single-service failure does not affect the overall display */
  } finally {
    detecting.value = false
  }
}

/** 打开密钥设置弹窗。Open the API Key modal. */
function openKeyModal(section: string, profile: string) {
  showKey.value = false
  keyModal.value = { section, profile, value: '' }
}
/** 获取当前密钥对应的环境变量名（提示用户可通过 env 配置）。Get the env var name for the current key (hints that env config is available). */
function keyEnvHint(): string {
  const m = keyModal.value
  if (!m) return ''
  return (editable.value as any)?.[m.section]?.profiles?.[m.profile]?.api_key_env || ''
}
/** 确认保存 API Key（通过 PUT secret 接口）。Confirm and save the API Key via the PUT secret endpoint. */
async function confirmKey() {
  const m = keyModal.value
  if (!m) return
  const path = `${m.section}.profiles.${m.profile}`
  const label = `${m.section} · ${m.profile}`
  try {
    const r = await api.putSecret(path, m.value)
    if (r.ok) {
      if (r.set) notify.ok(`已设置 ${label} 密钥（即时生效）`)
      else notify.ok(`已清除 ${label} 密钥`)
      const s = (editable.value as any)?.[m.section]
      if (s?.api_key_set) s.api_key_set[m.profile] = r.set
      keyModal.value = null
    } else {
      notify.err('设置密钥失败：' + (r.error || ''))
    }
  } catch (e) {
    notify.err('设置密钥失败：' + formatError(e))
  }
}
/** 清除当前 API Key（value 置空后调用 confirmKey）。Clear the current API Key (empties the value then calls confirmKey). */
async function clearKey() {
  const m = keyModal.value
  if (!m) return
  m.value = ''
  await confirmKey()
}

/** 从后端拉取厂商目录预设（失败不阻塞设置页）。Fetch the vendor catalog (failure does not block the settings page). */
async function loadCatalog() {
  try {
    const r = await api.getProviders()
    if (r.ok) catalog.value = r.catalog
  } catch { /* 目录拉取失败不阻塞设置页 / Catalog failure does not block the settings page */ }
}

/**
 * 设置页状态与操作入口（模块级单例）。
 * Settings-page state and operations (module-level singleton).
 *
 * @returns 状态引用与操作函数。State refs and operation functions.
 */
export function useSettings() {
  return {
    app, editable, saving, detecting, connResults, issues, catalog,
    addingSection, customAdding, customName, activeMenu, keyModal, showKey,
    sec, ed, menuDot, activeProfile, vendorPreset, vendorList, modelOptions, voiceOptions,
    presetToProfile, toggleAdding, confirmCustom, addProfileFromVendor, deleteProfile,
    fetchModelsFor, saveModule, load, detectAll, detectOne,
    openKeyModal, keyEnvHint, confirmKey, clearKey, loadCatalog,
  }
}
```

- [ ] **Step 3: 类型检查（此时文件未被引用，仅确认自身无类型错误）**

Run: `cd web && npx vue-tsc --noEmit`
Expected: 无错误。若报 `advancedDefs` 的 `fields` 类型不匹配，按 `AdvancedDef.fields` 的 `readonly (readonly [string, 'number'|'bool'|'text'])[]` 调整字面量，**不要**改回 `as const`。

- [ ] **Step 4: 提交**

```bash
git add web/src/components/console/settings/configDefs.ts web/src/components/console/settings/useSettings.ts
git commit -m "refactor(设置页): 抽出配置元数据与状态单例

- configDefs.ts: 模块/字段/标签单一来源（纯数据，无 Vue 依赖）
- useSettings.ts: 全部状态与 API 操作收敛为模块级单例
- msg/restartHint 字符串状态改为 notify 调用，删除 isErr() 字符串嗅探
- 错误文案统一全角，异常统一走 formatError（消除 (e?.message || '') 手写）"
```

---

## Task 4: 拆分设置页视图组件（3a 下半）

**Files:**
- Create: `web/src/components/console/settings/ServiceCard.vue`, `VoiceCard.vue`, `AdvancedCard.vue`, `VendorPicker.vue`, `ApiKeyModal.vue`
- Modify: `web/src/components/console/ConsoleSettings.vue`（重写为编排壳）

**Interfaces:**
- Consumes: Task 3 的 `useSettings()`、`configDefs.ts`；Task 2 的 `UiErrorNote` / `notify`
- Produces: 五个展示组件；`ConsoleSettings.vue` 对外接口不变（仍由 `ConsolePage.vue` 按 tab 懒加载，无 props）

- [ ] **Step 1: 创建 `VendorPicker.vue`**

模板取自原 `ConsoleSettings.vue:75-89`，CSS 取自 `.cs-vendor*`（702–715）+ `.cs-vendor-custom :deep(.ui-input)`（720）：

```vue
<template>
  <!-- 厂商目录选择面板（新增 Profile）：从预设厂商快速创建配置。Vendor catalog panel (add Profile): quickly create config from vendor presets. -->
  <div class="cs-vendor">
    <p class="cs-vendor-tip">从厂商目录新增 Profile（自动预填端点/模型，可再手动调整）</p>
    <!-- 自定义名称内联输入（替代 window.prompt）。Custom name inline input (replaces window.prompt). -->
    <div v-if="customAdding === sectionKey" class="cs-vendor-custom">
      <UiInput v-model="customName" placeholder="Profile 名称（如 my-gateway）" @keyup.enter="confirmCustom(sectionKey)" />
      <UiButton variant="primary" size="sm" @click="confirmCustom(sectionKey)">创建</UiButton>
      <UiButton variant="secondary" size="sm" @click="customAdding = null">取消</UiButton>
    </div>
    <div v-else class="cs-vendor-grid">
      <button class="cs-vendor-chip custom" @click="customAdding = sectionKey">＋ 自定义（空白）</button>
      <button v-for="v in vendorList(sectionKey)" :key="v.id" class="cs-vendor-chip" @click="addProfileFromVendor(sectionKey, v)">
        {{ v.label }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { UiButton, UiInput } from '../../ui'
import { useSettings } from './useSettings'
import type { ProviderPreset } from '../../../types'

/** 组件 props：所属模块 key。Component props: the owning module key. */
const props = defineProps<{ sectionKey: string }>()

/** 设置页单例状态与操作。Settings singleton state and operations. */
const { customAdding, customName, confirmCustom, addProfileFromVendor, vendorList } = useSettings()

/** 所属模块 key（模板中直接用，避免每处写 props.）。The owning module key (used directly in the template). */
const sectionKey = props.sectionKey
</script>

<style scoped>
.cs-vendor {
  border: 1px dashed var(--border-soft); border-radius: var(--r-sm);
  padding: 8px 10px; background: rgba(15, 23, 42, .4);
}
.cs-vendor-tip { font-size: var(--fs-2xs); color: var(--text-3); margin: 0 0 7px; }
.cs-vendor-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.cs-vendor-chip {
  font-size: var(--fs-2xs); font-family: var(--font-mono); color: var(--text-2);
  background: rgba(15, 23, 42, .6); border: 1px solid var(--border-soft);
  border-radius: var(--r-full); padding: 3px 10px; cursor: pointer;
}
.cs-vendor-chip:hover { color: var(--brand-c2); border-color: var(--brand-c2); }
.cs-vendor-chip.custom { border-style: dashed; color: var(--brand-c2); }
.cs-vendor-custom { display: flex; align-items: center; gap: 8px; }
.cs-vendor-custom :deep(.ui-input) { flex: 1; min-width: 0; }
</style>
```

> **关键约束（五个子组件通用）**：`<script setup>` 中**不要解构** `useSettings()` 的返回值——解构会拆掉 ref 的响应式连接，模板里 `customAdding` 也将失去 `.value` 语义。必须保留 `const s = useSettings()` 对象引用，模板中一律写 `s.customAdding.value`、`s.customName`、`s.confirmCustom(...)`。若发现 `s.xxx.value` 写法冗长想改用解构，**不要改**——那会破坏响应式。

- [ ] **Step 2: 创建 `ApiKeyModal.vue`**

模板取自原 `193-213`，CSS 取自 `.cs-dialog-*`（760–763）+ `.cs-key-input`（761）+ `.cs-key-input :deep(.ui-input)`（721）：

```vue
<template>
  <!-- 密钥弹出框（替代 window.prompt）：安全设置/清除 API Key。API Key modal (replaces window.prompt): securely set/clear API keys. -->
  <UiModal :model-value="!!s.keyModal.value" @update:model-value="v => { if (!v) s.keyModal.value = null }" title="设置 API Key">
    <p class="cs-dialog-sub">{{ s.keyModal.value?.section }} · {{ s.keyModal.value?.profile }}</p>
    <div class="cs-key-input">
      <UiInput
        :type="s.showKey.value ? 'text' : 'password'"
        :model-value="s.keyModal.value ? s.keyModal.value.value : ''"
        @update:model-value="v => { const m = s.keyModal.value; if (m) m.value = v }"
        placeholder="粘贴 API Key（留空 = 清除）"
        autofocus
      />
      <UiButton variant="secondary" size="sm" @click="s.showKey.value = !s.showKey.value">{{ s.showKey.value ? '隐藏' : '显示' }}</UiButton>
    </div>
    <p v-if="s.keyEnvHint()" class="cs-dialog-env">
      也可通过环境变量 <code>{{ s.keyEnvHint() }}</code> 配置（优先级高于此密钥）
    </p>
    <div class="cs-dialog-btns">
      <UiButton variant="ghost" size="sm" @click="s.clearKey">清除</UiButton>
      <UiButton variant="primary" size="sm" @click="s.confirmKey">保存</UiButton>
      <UiButton variant="ghost" size="sm" @click="s.keyModal.value = null">取消</UiButton>
    </div>
  </UiModal>
</template>

<script setup lang="ts">
import { UiButton, UiInput, UiModal } from '../../ui'
import { useSettings } from './useSettings'

/** 设置页单例状态与操作。Settings singleton state and operations. */
const s = useSettings()
</script>

<style scoped>
.cs-dialog-sub { font-size: var(--fs-2xs); color: var(--text-3); margin: 0; font-family: var(--font-mono); }
.cs-key-input { display: flex; align-items: center; gap: 8px; }
.cs-key-input :deep(.ui-input) { flex: 1; min-width: 0; }
.cs-dialog-env { font-size: var(--fs-2xs); color: var(--text-3); margin: 0; line-height: 1.6; }
.cs-dialog-env code { font-family: var(--font-mono); color: var(--brand-c2); }
.cs-dialog-btns { display: flex; justify-content: flex-end; gap: 8px; }
</style>
```

- [ ] **Step 3: 创建 `VoiceCard.vue`**

模板取自原 `132-158`，CSS 取 `.cs-card`（692）、`.cs-card-head`（693）、`.cs-card-title`（694–697）、`.cs-tts`（729）：

```vue
<template>
  <!-- 语音模块：唤醒词 + VAD + 本地播报配置。Voice module: wake word + VAD + local speech settings. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">语音（唤醒 / 静音检测）</span>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule('voice')">
        {{ s.saving.value ? '保存中…' : '保存' }}
      </UiButton>
    </div>
    <SettingsField v-if="s.editable.value" label="唤醒启用" row>
      <UiToggle :model-value="s.ed().wake_word.enabled" @update:model-value="v => (s.ed().wake_word.enabled = v)" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="唤醒词">
      <UiInput v-model="s.ed().wake_word.keyword" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="灵敏度（0-1）">
      <UiInput type="number" step="0.05" min="0" max="1" :model-value="s.ed().wake_word.sensitivity" @update:model-value="v => (s.ed().wake_word.sensitivity = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="静音判定阈值">
      <UiInput type="number" step="0.01" :model-value="s.ed().vad.silence_threshold" @update:model-value="v => (s.ed().vad.silence_threshold = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="静音停止时长（ms）">
      <UiInput type="number" :model-value="s.ed().vad.silence_duration_ms" @update:model-value="v => (s.ed().vad.silence_duration_ms = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="最长录音（ms）">
      <UiInput type="number" :model-value="s.ed().vad.max_duration_ms" @update:model-value="v => (s.ed().vad.max_duration_ms = toNum(v))" />
    </SettingsField>
    <div class="cs-tts"><TtsSettings /></div>
  </UiCard>
</template>

<script setup lang="ts">
import TtsSettings from '../../assistant/TtsSettings.vue'
import SettingsField from './SettingsField.vue'
import { UiButton, UiCard, UiInput, UiToggle } from '../../ui'
import { useSettings } from './useSettings'

/** 设置页单例状态与操作。Settings singleton state and operations. */
const s = useSettings()

/**
 * 数值输入：保留空串（清空），其余转 number（与原生 v-model.number 行为一致）。
 * Numeric input: keep the empty string (cleared), otherwise convert to number.
 *
 * @param v 输入框原值。The raw input value.
 * @returns 数值或空串。The number, or an empty string.
 */
function toNum(v: string): number | '' {
  return v === '' ? '' : Number(v)
}
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  letter-spacing: .02em;
}
.cs-tts { margin-top: 2px; }
</style>
```

- [ ] **Step 4: 创建 `AdvancedCard.vue`**

模板取自原 `161-183`，CSS 取 `.cs-card*`（同上）、`.cs-subcard*`（731–740）、`.cs-note`（754–757）：

```vue
<template>
  <!-- 高级模块：Agent / LLM 客户端 / 工具 / RAG / 服务器参数配置。Advanced module: Agent / LLM client / Tools / RAG / Server settings. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">高级设置（Agent / LLM 客户端 / 工具 / 服务器 / MCP）</span>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule('advanced')">
        {{ s.saving.value ? '保存中…' : '保存' }}
      </UiButton>
    </div>
    <div v-for="d in advancedDefs" :key="d.key" class="cs-subcard">
      <div class="cs-subcard-title">{{ d.title }}</div>
      <template v-for="f in d.fields" :key="f[0]">
        <SettingsField v-if="f[1] === 'bool'" :label="fieldLabel(f[0])" row>
          <UiToggle :model-value="s.sec(d.key)[f[0]]" @update:model-value="v => (s.sec(d.key)[f[0]] = v)" />
        </SettingsField>
        <SettingsField v-else :label="fieldLabel(f[0])">
          <UiInput :type="f[1] === 'number' ? 'number' : 'text'" v-model="s.sec(d.key)[f[0]]" />
        </SettingsField>
      </template>
    </div>
    <p class="cs-note">
      MCP server 列表、服务器 host/port/api_token 建议直接编辑 config.yaml / config.secrets.yaml（改动需重启生效）。
      密钥只报「已设置 / 未设置」，永不回显。
    </p>
  </UiCard>
</template>

<script setup lang="ts">
import SettingsField from './SettingsField.vue'
import { UiButton, UiCard, UiInput, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { advancedDefs, fieldLabel } from './configDefs'

/** 设置页单例状态与操作。Settings singleton state and operations. */
const s = useSettings()
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  letter-spacing: .02em;
}
.cs-subcard {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border-soft); border-radius: var(--r-md);
  background: rgba(15, 23, 42, .4);
}
.cs-subcard-title {
  font-size: var(--fs-xs); font-weight: 600; color: var(--text-2);
  letter-spacing: .02em;
}
.cs-note {
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6;
  margin: 4px 0 0;
}
</style>
```

- [ ] **Step 5: 创建 `ServiceCard.vue`**

模板取自原 `44-128`（`<UiCard>` 内部），CSS 取 `.cs-card*`、`.cs-profrow`（700）、`.cs-profrow :deep(.ui-btn.on)`（743）、`.cs-keyrow`（717）、`.cs-connline`（723–727）、`.st-*`（688–690）：

```vue
<template>
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">{{ section.title }}</span>
      <div class="cs-card-btns">
        <UiButton variant="secondary" size="sm" :disabled="s.detecting.value" @click="s.detectOne(section.name)">测试连接</UiButton>
        <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule(section.key)">
          {{ s.saving.value ? '保存中…' : '保存' }}
        </UiButton>
      </div>
    </div>

    <SettingsField v-if="section.toggle" label="启用" row>
      <UiToggle :model-value="s.sec(section.key).enabled" @update:model-value="v => (s.sec(section.key).enabled = v)" />
    </SettingsField>

    <!-- Profile 管理：切换 / 新增（厂商目录） / 删除。Profile management: switch / add from vendor catalog / delete. -->
    <div class="cs-profrow">
      <SettingsField label="Profile" grow>
        <UiSelect :model-value="s.sec(section.key).active" @update:model-value="v => (s.sec(section.key).active = v)">
          <option v-for="n in Object.keys(s.sec(section.key).profiles)" :key="n" :value="n">{{ n }}</option>
        </UiSelect>
      </SettingsField>
      <UiButton variant="secondary" size="sm" :class="{ on: s.addingSection.value === section.key }" @click="s.toggleAdding(section.key)">
        <UiIcon name="plus" :size="12" /> 新增
      </UiButton>
      <UiButton variant="secondary" size="sm" :disabled="Object.keys(s.sec(section.key).profiles).length <= 1" @click="s.deleteProfile(section.key)">
        <UiIcon name="trash" :size="12" /> 删除
      </UiButton>
    </div>

    <VendorPicker v-if="s.addingSection.value === section.key" :section-key="section.key" />

    <template v-for="f in section.fields" :key="f">
      <SettingsField :label="fieldLabel(f)">
        <!-- 协议下拉：选择 OpenAI 兼容 / Anthropic / Gemini。Protocol dropdown: choose OpenAI compatible / Anthropic / Gemini. -->
        <UiSelect v-if="f === 'provider'" :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)">
          <option value="openai">OpenAI 兼容</option>
          <option value="anthropic">Anthropic（原生）</option>
          <option value="gemini">Gemini（原生）</option>
        </UiSelect>
        <!-- 模型 / 音色可输入下拉：支持手动输入或从列表选择。Model / voice input with datalist. -->
        <template v-else-if="f === 'model' || f === 'voice'">
          <UiInput :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)" :list="`dl-${section.key}-${f}`" />
          <datalist :id="`dl-${section.key}-${f}`">
            <option v-for="m in (f === 'model' ? s.modelOptions(section) : s.voiceOptions(section))" :key="m" :value="m" />
          </datalist>
        </template>
        <UiInput
          v-else
          :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]"
          @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)"
          :type="isNumericField(f) ? 'number' : 'text'"
          :step="isNumericField(f) ? (f === 'temperature' ? 0.1 : 1) : undefined"
        />
      </SettingsField>
    </template>

    <div class="cs-keyrow">
      <UiChip :tone="s.sec(section.key).api_key_set[s.sec(section.key).active] ? 'ok' : 'warn'" :dot="false">
        API Key：{{ s.sec(section.key).api_key_set[s.sec(section.key).active] ? '已设置' : '未设置' }}
      </UiChip>
      <UiButton variant="secondary" size="sm" @click="s.openKeyModal(section.key, s.sec(section.key).active)">设置</UiButton>
      <UiButton variant="secondary" size="sm" @click="s.fetchModelsFor(section)">获取模型</UiButton>
    </div>

    <div v-if="s.connResults.value[section.name]" class="cs-connline" :class="'st-' + s.connResults.value[section.name].status">
      {{ s.connResults.value[section.name].detail || s.connResults.value[section.name].status }}
      <em v-if="s.connResults.value[section.name].latency_ms != null">{{ s.connResults.value[section.name].latency_ms }}ms</em>
    </div>
  </UiCard>
</template>

<script setup lang="ts">
import SettingsField from './SettingsField.vue'
import VendorPicker from './VendorPicker.vue'
import { UiButton, UiCard, UiChip, UiIcon, UiInput, UiSelect, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { fieldLabel, isNumericField, type SectionDef } from './configDefs'

/** 组件 props：服务模块定义。Component props: the service module definition. */
defineProps<{ section: SectionDef }>()

/** 设置页单例状态与操作。Settings singleton state and operations. */
const s = useSettings()
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  letter-spacing: .02em;
}
.cs-card-btns { display: flex; align-items: center; gap: 8px; }
.cs-profrow { display: flex; align-items: flex-end; gap: 8px; }
.cs-profrow :deep(.ui-btn.on) { color: var(--brand-c2); border-color: var(--brand-c2); }
.cs-keyrow { display: flex; align-items: center; gap: 8px; }
.cs-connline {
  font-size: var(--fs-2xs); color: var(--text-3);
  border-top: 1px dashed var(--border-soft); padding-top: 7px;
}
.cs-connline em { font-style: normal; font-family: var(--font-mono); color: var(--brand-c2); margin-left: 6px; }
.st-ok { color: #34d399 !important; border-color: rgba(52, 211, 153, .4) !important; background: rgba(52, 211, 153, .07); }
.st-skip { color: var(--text-3) !important; }
.st-fail { color: #f87171 !important; border-color: rgba(248, 113, 113, .4) !important; background: rgba(248, 113, 113, .07); }
</style>
```

- [ ] **Step 6: 重写 `ConsoleSettings.vue` 为编排壳**

保留：头部（原 3–7）、左菜单（10–28）、消息条位置（改为 toast，故删除）、连接状态条（35–40）、issues（186–188）、组装区。**删除** `cs-msg` / `cs-restart` 元素（改由 toast 承担），**删除** `isErr` / `connTone` / `connStatusText` 之外的重复逻辑（`connTone` / `connStatusText` 保留在壳内，因为只在连接状态条用到）。

```vue
<template>
  <div class="console-settings">
    <!-- 设置页头部：标题和说明文字。Settings page header: title and description. -->
    <div class="cs-head">
      <h2 class="cs-title"><UiIcon name="settings" :size="17" /> 设置</h2>
      <p class="cs-sub">左侧菜单切换模块，每个模块独立「保存 / 测试连接」，密钥通过弹出框设置</p>
    </div>

    <div class="cs-body">
      <!-- 左侧菜单：模块切换（LLM / ASR / TTS / 语音唤醒 / 高级设置）。Left sidebar menu: module switching. -->
      <aside class="cs-menu">
        <button
          v-for="m in menuDefs"
          :key="m.id"
          class="cs-menu-item"
          :class="{ on: s.activeMenu.value === m.id }"
          @click="s.activeMenu.value = m.id"
        >
          <UiIcon :name="m.icon" :size="14" />
          <span>{{ m.label }}</span>
          <i class="cs-menu-dot" :class="{ on: s.menuDot(m.id) }" title="密钥已设置"></i>
        </button>
        <div class="cs-menu-extra">
          <UiButton variant="secondary" size="sm" :disabled="s.detecting.value" @click="s.detectAll" block>
            {{ s.detecting.value ? '检测中…' : '检测全部' }}
          </UiButton>
        </div>
      </aside>

      <!-- 右侧内容区域：根据左侧菜单选择展示对应模块配置。Right content area: shows the module matching the left menu. -->
      <div class="cs-main">
        <!-- 连接状态条：展示各服务模块的连通性检测结果。Connection status bar: connectivity results per service module. -->
        <div v-if="Object.keys(s.connResults.value).length" class="cs-conn">
          <UiChip v-for="c in Object.values(s.connResults.value)" :key="c.name" :tone="connTone(c.status)" :dot="false">
            {{ c.name }} {{ connStatusText(c.status) }}
          </UiChip>
        </div>

        <!-- 服务模块：LLM / ASR / TTS（仅在 activeMenu 匹配时显示）。Service modules: LLM / ASR / TTS. -->
        <ServiceCard
          v-for="sec_ in sectionDefs"
          v-show="s.activeMenu.value === sec_.key"
          :key="sec_.key"
          :section="sec_"
        />

        <!-- 语音模块：唤醒词 + VAD + 本地播报。Voice module: wake word + VAD + local speech. -->
        <VoiceCard v-if="s.activeMenu.value === 'voice'" />

        <!-- 高级模块：Agent / LLM 客户端 / 工具 / 服务器 参数。Advanced module settings. -->
        <AdvancedCard v-if="s.activeMenu.value === 'advanced'" />

        <!-- 配置校验问题：检测到的错误和警告列表。Config validation issues: detected errors and warnings. -->
        <div v-if="s.issues.value.length" class="cs-issues">
          <p v-for="i in s.issues.value" :key="i.key" :class="'lv-' + i.level">[{{ i.level }}] {{ i.key }}：{{ i.message }}</p>
        </div>
      </div>
    </div>

    <ApiKeyModal />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import AdvancedCard from './settings/AdvancedCard.vue'
import ApiKeyModal from './settings/ApiKeyModal.vue'
import ServiceCard from './settings/ServiceCard.vue'
import VoiceCard from './settings/VoiceCard.vue'
import { useSettings } from './settings/useSettings'
import { menuDefs, sectionDefs } from './settings/configDefs'
import { UiButton, UiChip, UiIcon } from '../ui'

/** 设置页单例状态与操作。Settings singleton state and operations. */
const s = useSettings()

/**
 * 将连通性状态映射为 UI 色调。
 * Map a connectivity status to a UI tone.
 *
 * @param status 连通性状态。Connectivity status.
 * @returns UI 色调。The UI tone.
 */
function connTone(status: string): 'ok' | 'warn' | 'err' | 'info' | 'neutral' {
  return status === 'ok' ? 'ok' : status === 'skip' ? 'neutral' : 'err'
}

/**
 * 将连通性状态转为中文文本。
 * Convert a connectivity status to Chinese text.
 *
 * @param status 连通性状态。Connectivity status.
 * @returns 中文状态文本。The Chinese status text.
 */
function connStatusText(status: string): string {
  return status === 'ok' ? '✓ 连通' : status === 'skip' ? '跳过' : '✗ 失败'
}

// 单例 state 跨挂载存活，故每次进入设置页都重新拉取，避免展示陈旧配置。
// The singleton state survives mount/unmount, so re-fetch on every entry.
onMounted(() => { s.load(); s.loadCatalog() })
</script>

<style scoped>
.console-settings {
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px; flex: 1; min-height: 0; overflow-y: auto;}
.cs-head { display: flex; flex-direction: column; gap: 4px; }
.cs-title {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: var(--fs-lg); font-weight: 700; letter-spacing: .03em;
  color: var(--text-1); margin: 0;
}
.cs-title :deep(svg) { color: var(--brand-c2); }
.cs-sub { font-size: var(--fs-xs); color: var(--text-3); margin: 0; }

/* ── 左菜单 + 右内容 ── */
.cs-body { display: flex; gap: 16px; align-items: flex-start; }
.cs-menu {
  width: 148px; flex-shrink: 0; position: sticky; top: 12px;
  display: flex; flex-direction: column; gap: 3px;
}
.cs-menu-item {
  display: flex; align-items: center; gap: 8px;
  font-size: var(--fs-xs); color: var(--text-2); text-align: left;
  background: rgba(15, 23, 42, .55); border: 1px solid transparent;
  border-radius: var(--r-sm); padding: 7px 10px; cursor: pointer;
  transition: color var(--dur-fast), border-color var(--dur-fast), background var(--dur-fast);
}
.cs-menu-item:hover { color: var(--brand-c2); }
.cs-menu-item.on {
  color: var(--brand-c2); border-color: var(--brand-c2);
  background: rgba(11, 17, 32, .75);
}
.cs-menu-dot {
  margin-left: auto; width: 7px; height: 7px; border-radius: 50%;
  background: rgba(148, 163, 184, .25);
}
.cs-menu-dot.on { background: #34d399; box-shadow: 0 0 6px rgba(52, 211, 153, .6); }
.cs-menu-extra { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border-soft); }

.cs-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }

.cs-conn { display: flex; gap: 8px; flex-wrap: wrap; }

.cs-issues { display: flex; flex-direction: column; gap: 6px; }
.cs-issues p {
  font-size: var(--fs-2xs); margin: 0; line-height: 1.5;
  border-radius: var(--r-sm); padding: 6px 9px;
}
.lv-error { color: #f87171; background: rgba(248, 113, 113, .07); }
.lv-warning { color: #fbbf24; background: rgba(251, 191, 36, .07); }
.lv-info { color: var(--text-3); background: rgba(148, 163, 184, .07); }
</style>
```

> **实现提示**：`v-for` 里的 `sec_` 是刻意命名，避免与 `useSettings()` 返回的 `sec()` 函数冲突。`v-show` 而非 `v-if` 用于 ServiceCard：三个服务卡共享同一份 DOM 结构，`v-if` 会反复销毁/重建表单导致输入焦点丢失——若实测无此问题，可改回 `v-if` 以贴近原实现。

- [ ] **Step 7: 类型检查与构建**

Run: `cd web && npm run build`
Expected: `vue-tsc` 无错误；vite 构建成功。若有 `s.xxx.value` 相关的响应式告警或类型错误，逐个修正**而不是**改回解构。

- [ ] **Step 8: 提交**

```bash
git add web/src/components/console/ConsoleSettings.vue web/src/components/console/settings/
git commit -m "refactor(设置页): 拆分为 5 个子组件 + 编排壳

ConsoleSettings.vue 765 行 → 编排壳 + settings/ 下 5 个视图组件。
- ServiceCard: LLM/ASR/TTS 服务卡（含 Profile 管理与连通性行）
- VoiceCard: 唤醒 / VAD / TTS
- AdvancedCard: 高级设置 5 子卡
- VendorPicker: 厂商目录面板
- ApiKeyModal: 密钥弹窗
状态经 useSettings() 单例共享，子组件不解构以保持响应式。
scoped 样式按组件边界搬运（scoped 不下传）。"
```

---

## Task 5: 迁移 console 组件到统一错误处理（3b 下半）

**Files:**
- Modify: `web/src/components/console/ConsoleConversation.vue`、`ConsoleEnvView.vue`、`ConsoleHistory.vue`、`ConsoleMemoryView.vue`、`ConsoleScheduleView.vue`、`ConsoleStatus.vue`、`ConsoleTaskView.vue`、`ConsoleTools.vue`

**Interfaces:**
- Consumes: Task 2 的 `useAsync` / `notify` / `formatError` / `UiErrorNote`
- Produces: 无新接口

> **迁移模式**（对每个组件重复）：
> 1. 删除本地的 `const error = ref('')`（或同等命名的错误 ref）与 `const loading = ref(false)`（若仅用于加载）；
> 2. 把"拉取数据"的 `try/catch` 换成 `useAsync`，模板中的 `v-else-if="error"` 换成 `<UiErrorNote :error="error" />`；
> 3. "操作类"（删除 / 新增 / 重命名 / 归档 / 清空 / 新建）的失败分支改为 `notify.err('X失败：' + formatError(e))`，成功分支按需 `notify.ok(...)`；
> 4. 错误文案统一全角冒号；
> 5. `onMounted` / `watch` 中的调用改为调用 `run()`。

**逐组件的调用点分类**（行号为迁移前，已实测）：

| 组件 | 加载类 → `useAsync` + `<UiErrorNote>` | 操作类 → `notify` |
|---|---|---|
| `ConsoleTools.vue` | `api.getTools()` L42 | — |
| `ConsoleEnvView.vue` | `api.getEnv()` L28 | — |
| `ConsoleStatus.vue` | `api.ping()` L81 | — |
| `ConsoleConversation.vue` | — | `api.createSession()` L33 |
| `ConsoleTaskView.vue` | — | `api.answer()` L83、`api.stopTask()` L94 |
| `ConsoleMemoryView.vue` | `api.getMemory()` L35 | `api.deleteMemory()` L48 |
| `ConsoleScheduleView.vue` | `api.getSchedules()` L42 | `api.addSchedule()` L55、`api.deleteSchedule()` L67 |
| `ConsoleHistory.vue` | `api.listSessions()` L55、`api.getHistoryDetail()` L80 | `api.createSession()` L71、`api.clearSession()` L91、`api.archiveSession()` L99、`api.deleteSession()` L107、`api.renameSession()` L117 |

- [ ] **Step 1: 迁移 `ConsoleTools.vue`（模板范例，后续 7 个照此办理）**

替换该组件的错误处理段为：

```ts
import { useAsync } from '../../composables/useAsync'
import { UiErrorNote } from '../ui'

/** 工具清单加载：统一错误捕获与文案（替代本地 error ref + try/catch）。
 *  Tool list loading: unified error capture (replaces the local error ref + try/catch). */
const { data: tools, error, loading, run: loadTools } = useAsync(() => api.getTools())
```

改动要点：
1. 删除原有的 `const error = ref('')` 与包裹 `api.getTools()` 的 `try/catch`（原 `'加载失败: '` 半角拼接一并删除）；
2. `onMounted` 中的调用改为 `loadTools()`；
3. 模板中原 `v-else-if="error"` 的 `<div class="console-empty">加载失败：{{ error }}</div>` 替换为 `<UiErrorNote v-else-if="error" :error="error" />`；
4. 模板中对工具数据的所有引用改用 `tools`（原先的变量名按实际文件中 `data`/`list` 等命名对应替换）。

验证：`cd web && npm run build` → 通过。

- [ ] **Step 2: 迁移三个纯加载组件：`ConsoleEnvView.vue`、`ConsoleStatus.vue`、`ConsoleTools` 同类**

对 `ConsoleEnvView.vue`：

```ts
const { data: env, error, run: loadEnv } = useAsync(() => api.getEnv())
```

对 `ConsoleStatus.vue`：

```ts
const { data: ping, error, run: loadPing } = useAsync(() => api.ping())
```

两者均照 Step 1 的四步要点执行（删本地 `error` ref 与 try/catch、`onMounted` 改调 `run()`、模板内联错误换 `<UiErrorNote :error="error" />`、引用改名）。

> 注意 `ConsoleStatus.vue` 的 ping 是延迟探针，原实现可能把失败当作「离线」正常态而非错误。迁移前先读该文件确认：**若失败已被业务语义吸收（显示为离线状态），保留原行为，不要强行套 `<UiErrorNote>`**。

验证：`cd web && npm run build` → 通过。

- [ ] **Step 3: 迁移 `ConsoleMemoryView.vue` 与 `ConsoleScheduleView.vue`（加载 + 操作混合）**

`ConsoleMemoryView.vue`：

```ts
/** 记忆列表加载。Memory list loading. */
const { data: facts, error, run: loadMemory } = useAsync(() => api.getMemory())
```

删除记忆（L48）的操作分支：

```ts
try {
  await api.deleteMemory(topic)
  notify.ok(`已删除记忆「${topic}」`)
  await loadMemory()
} catch (e) {
  notify.err('删除失败：' + formatError(e))
}
```

`ConsoleScheduleView.vue` 同构：`getSchedules` → `useAsync`；`addSchedule` / `deleteSchedule` → 上面的 `notify` 模式，成功文案分别为 `已注册定时任务` / `已取消定时任务`。

验证：`cd web && npm run build` → 通过。

- [ ] **Step 4: 迁移 `ConsoleHistory.vue`（7 个调用，最重）**

加载类：`api.listSessions()`（L55）与 `api.getHistoryDetail()`（L80）各自包一个 `useAsync`。

操作类 5 个（L71 / L91 / L99 / L107 / L117）统一改写为：

```ts
/**
 * 执行一次会话操作并统一反馈。
 * Run a session operation with unified feedback.
 *
 * @param label 操作名（用于文案）。Operation name (for the message).
 * @param fn 实际操作。The actual operation.
 */
async function act(label: string, fn: () => Promise<unknown>): Promise<void> {
  try {
    await fn()
    notify.ok(`${label}成功`)
    await loadSessions()
  } catch (e) {
    notify.err(`${label}失败：` + formatError(e))
  }
}
```

调用点示例：`await act('重命名', () => api.renameSession(id, name))`、`await act('归档', () => api.archiveSession(id, true))`、`await act('清空', () => api.clearSession(id))`、`await act('删除', () => api.deleteSession(id))`、`await act('新建会话', () => api.createSession())`。

`loadSessions` 替换为该组件内 `useAsync` 的 `run` 别名。

验证：`cd web && npm run build` → 通过。

- [ ] **Step 5: 迁移 `ConsoleConversation.vue` 与 `ConsoleTaskView.vue`（纯操作）**

`ConsoleConversation.vue` 的 `api.createSession()`（L33）与 `ConsoleTaskView.vue` 的 `api.answer()`（L83）、`api.stopTask()`（L94）——三者都是操作类，直接套 Step 4 的 `act()` 模式（可各自在组件内定义一个同签名的局部 `act`），或按其现有错误处理位置替换为 `notify.err('X失败：' + formatError(e))`。

验证：`cd web && npm run build` → 通过。

- [ ] **Step 6: 检查是否还有遗漏的旧写法**

Run:
```bash
cd web && grep -rn "加载失败: " src/ ; grep -rn "e?.message || ''" src/ ; grep -rn "const error = ref" src/components/console/
```
Expected: 三条命令均无输出（`ConsoleSettings` 的 `isErr` 已在 Task 3 删除；半角冒号与手写 `e?.message` 已全部收敛）

- [ ] **Step 7: 全量回归**

Run: `cd web && npm test && npm run build`
Expected: Vitest 全部通过；vue-tsc 无错误；构建成功

- [ ] **Step 8: 人工验证（不可省）**

启动 `python main.py serve`，打开控制台，逐个 tab 检查：对话 / 任务 / 状态 / 工具 / 统计 / 环境 / 记忆 / 设置 / 历史 / 定时。

重点确认：
- 设置页五个模块（LLM / ASR / TTS / 语音唤醒 / 高级）渲染与拆分前一致；
- 保存 / 检测全部 / 新增 Profile / 设置密钥的提示以浮层出现且文案为全角冒号；
- 主动制造一次失败（如断网后点「检测全部」）确认 toast 显示错误文案。

- [ ] **Step 9: 提交**

```bash
git add web/src/components/console/
git commit -m "refactor(前端): console 组件迁移到统一错误处理

8 个组件从各自为政的 try/catch 迁移到 useAsync + UiErrorNote（加载类）
与 notify（操作类），删除本地 error ref 与重复样板。
错误文案统一全角冒号，异常统一走 formatError。"
```

---

## Task 6: 全量验证与收尾

**Files:**
- Modify: `README.md`（工具数 26 → 27；测试文件数 36 → 40+）、`docs/architecture/roadmap.md`（测试文件数同步）

- [ ] **Step 1: 后端全量**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过；mypy 80 文件无问题

- [ ] **Step 2: 前端全量**

Run: `cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 3: 确认 API 类型无需重新生成**

Run:
```bash
cd web && PYTHONIOENCODING=utf-8 python ../scripts/gen_openapi.py && npx --yes openapi-typescript@7.13.0 src/api/openapi.json -o /tmp/gen-check.ts && (git diff --quiet src/api/generated.ts && echo "OK: 无 schema 变更")
```
Expected: 输出 `OK: 无 schema 变更`

- [ ] **Step 4: 同步文档数字**

`README.md` 中「26 个内置工具」改为 `27`（实测 `@tool(` 装饰器 27 处）；`docs/architecture/roadmap.md` 中「36 个 pytest 文件」改为当前实际数量（步骤：`ls tests/*.py | wc -l`）。

- [ ] **Step 5: 提交并推送**

```bash
git add README.md docs/architecture/roadmap.md
git commit -m "docs: 同步工具数与测试文件数

README 内置工具 26 → 27（实测 @tool 装饰器 27 处）；
roadmap 测试文件数同步到当前值。"
git push origin main
```

---

## 完成标准

- [ ] `python -m pytest tests/ -q` 全绿，含新增 GC 回归用例
- [ ] `python -m mypy core/ server.py` 无问题
- [ ] `cd web && npm test` 全绿（原 7 例 + 新增 13 例）
- [ ] `cd web && npm run build` 无类型错误
- [ ] `ConsoleSettings.vue` ≤ 160 行，`settings/` 下 7 个文件各司其职
- [ ] `grep -rn "加载失败: " web/src/` 与 `grep -rn "e?.message || ''" web/src/` 均无输出
- [ ] 人工跑过控制台全部 10 个 tab，设置页五模块渲染无回归
