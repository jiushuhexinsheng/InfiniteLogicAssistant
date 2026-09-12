# 后端静默失败点修复 + 前端错误处理统一与设置页拆分 — 设计文档

日期：2026-09-12
状态：待审批

## 背景

对 `1d5e4db` 版本做全景分析后提出的 4 项问题，本次处理其中的第 2、3 项（第 1 项确认层否定感知已由 `fd61203` 修复，第 4 项前端测试基建单独立项）。

分析过程中有两处判断经复核后**更正**，记录如下，避免后续按错误前提施工：

| 原判断 | 复核结论 | 依据 |
|---|---|---|
| `ConsoleMessageList` / `ConsoleStats` 「没有 catch，静默失败」 | **判断错误**。两者是纯展示组件（只接 props、不调 API），没有东西可 catch | `ConsoleMessageList.vue:32` 仅 `defineProps`；`ConsoleStats.vue` 全文无 `api.` 调用 |
| `api/state.py` 的 `sweep()` 仅由 `register()` 驱动 → 空闲会话不被回收 | **不是真实缺陷**。SSE 生成器的 `finally` 已覆盖正常结束/编排异常/客户端断开三种路径 | `core/api/voice.py:221` `state.cleanup(session.id)`；且 `register()` 每次都会 `sweep()` |

因此本次第 2 项仅剩一个真实缺陷（2a），第 3 项**不是修 bug，而是收敛与标准化重构**。

## 已确认需求（决策记录）

| 项 | 决定 |
|---|---|
| 2b（`sweep` 驱动方式） | **撤销，不改**。已有 `voice.py:221` 的 `finally` cleanup 覆盖全部路径，再加周期性 sweep 属于重复防护（YAGNI） |
| 3b 错误处理范围 | **内联 + 全局 toast**：加载类错误内联展示（`useAsync` + `UiErrorNote`），操作类反馈走全局 toast |
| 3a 状态共享方式 | **模块级单例**（与 `useConsole.ts`、`assistant/store.ts` 现有先例一致） |
| 范围外 | 不改后端 API 契约；不引入 `jsdom` / `@vue/test-utils`；不动确认层（第 1 项已修） |

## 目标文件变更总览

```
后端（Python）
  core/orchestrator/pipeline.py        # 后台任务持引用（2a）
  tests/test_orchestrator_pipeline.py  # 新增 GC 回归测试

前端（Vue3 + TS）
  src/errors.ts                        # 新增：formatError 单一文案来源
  src/composables/useAsync.ts          # 新增：统一 loading/error/run
  src/composables/useToast.ts          # 新增：模块级单例通知队列
  src/components/ui/UiErrorNote.vue    # 新增：内联错误展示
  src/components/ui/UiToaster.vue      # 新增：toast 渲染容器
  src/components/ui/index.ts           # 导出上面两个原语
  src/App.vue                          # 挂载 <UiToaster />
  src/components/console/settings/configDefs.ts   # 新增：配置元数据（纯数据）
  src/components/console/settings/useSettings.ts  # 新增：设置页状态单例 + API 操作
  src/components/console/settings/ServiceCard.vue     # 新增：LLM/ASR/TTS 服务卡
  src/components/console/settings/VoiceCard.vue       # 新增：语音（唤醒/VAD/TTS）
  src/components/console/settings/AdvancedCard.vue    # 新增：高级设置
  src/components/console/settings/VendorPicker.vue    # 新增：厂商目录面板
  src/components/console/settings/ApiKeyModal.vue     # 新增：密钥弹窗
  src/components/console/ConsoleSettings.vue          # 瘦身为编排壳
  src/components/console/Console{Conversation,EnvView,History,MemoryView,
      ScheduleView,Status,TaskView,Tools}.vue         # 迁移到 useAsync / notify

测试（新增）
  web/src/errors.spec.ts
  web/src/composables/__tests__/useAsync.spec.ts
  web/src/composables/__tests__/useToast.spec.ts
```

## 详细设计

### 2a — 后台任务持引用（`core/orchestrator/pipeline.py`）

**问题**：`pipeline.py:148` 的 `asyncio.ensure_future(extract_and_store(...))` 未保留返回值。CPython 的事件循环对 Task 仅持**弱引用**，该任务可能在执行完成前被垃圾回收；`extract_and_store` 内部吞掉所有异常（`core/memory/extract.py:67`），因此后果是**长期记忆提取静默不发生**，无任何报错痕迹。

**方案**：模块级集合持有引用，完成后自动移除。

```python
# 后台任务引用集：asyncio 只对 Task 持弱引用，不留引用可能被 GC 掉（记忆提取静默丢失）
_bg_tasks: set[asyncio.Task] = set()

def _spawn_bg(coro) -> asyncio.Task:
    """启动后台任务并持有引用，完成后自动丢弃（防止被 GC）。"""
    t = asyncio.ensure_future(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)
    return t
```

`pipeline.py:148` 改为 `_spawn_bg(extract_and_store(task, result, get_facts_store()))`。

**不改**：不改变"不阻塞回复"的语义（仍为 fire-and-forget），不新增 await 点。

### 3a — 拆分 `ConsoleSettings.vue`

现状 765 行（template 215 / script 417 / style 131，另 2 行分隔）。拆为 8 个文件：

| 文件 | 约行数 | 内容 | 原位置 |
|---|---|---|---|
| `settings/configDefs.ts` | 50 | `menuDefs` / `sectionDefs` / `advancedDefs` / `NUMERIC` / `LABELS` + `fieldLabel()` / `isNumericField()` | 258–306, 317–323 |
| `settings/useSettings.ts` | 200 | 全部 ref 状态 + `load` / `saveModule` / `persistSection` / `detectAll` / `detectOne` / Profile 增删改 / `fetchModelsFor` / 密钥弹窗 / `loadCatalog`，及 `sec` / `ed` / `menuDot` / `activeProfile` / `vendorPreset` / `modelOptions` / `voiceOptions` / `presetToProfile` | 229–255, 309–315, 343–408, 428–500, 504–581, 586–630 |
| `settings/ServiceCard.vue` | 90 | LLM/ASR/TTS 服务卡 | template 43–129 |
| `settings/VoiceCard.vue` | 30 | 唤醒 / VAD / TTS | template 132–158 |
| `settings/AdvancedCard.vue` | 25 | 高级设置 5 个子卡 | template 161–183 |
| `settings/VendorPicker.vue` | 20 | 厂商目录面板 | template 75–89 |
| `settings/ApiKeyModal.vue` | 25 | 密钥弹窗 | template 193–213 |
| `ConsoleSettings.vue` | ~130 | 头部 + 左侧菜单 + 消息条 + 连接状态条 + issues + 组装 | 其余 |

**状态共享：模块级单例。** `useSettings()` 在模块顶层创建 state 并在调用间共享（与 `useConsole.ts` 的 `activeTab`、`assistant/store.ts` 同模式）。子组件各自 `useSettings()` 取值，无 prop 逐层传递。

单例的生命周期含义：state 跨 `ConsoleSettings` 挂载/卸载存活，因此**必须保留 `onMounted` 时重新 `load()`** 的现有行为，避免展示陈旧配置。此点写入实施清单。

**样式**：`<style scoped>` 不下传给子组件，`cs-*` 规则按组件边界搬运到各自的 scoped 块，父组件仅保留布局相关（`.console-settings` / `.cs-head` / `.cs-body` / `.cs-menu` / `.cs-main`）。CSS 为纯搬运，**视觉回归风险由人工比对承担**（见验证缺口）。

### 3b — 统一错误处理

**新增基础设施**

| 文件 | 职责 |
|---|---|
| `src/errors.ts` | `formatError(e: unknown): string` — 全站唯一错误文案来源（`Error` 取 `.message`，`string` 原样，其余 `String(e)`，空值回退「未知错误」） |
| `src/composables/useAsync.ts` | `const { data, error, loading, run } = useAsync(fn)`；内部 try/catch 统一走 `formatError`，消除 26 处重复样板 |
| `src/components/ui/UiErrorNote.vue` | 内联错误展示，统一 `.ui-errnote` 样式，替换现有 `加载失败：{{ error }}` 的散落写法 |
| `src/composables/useToast.ts` | 模块级单例队列，暴露 `notify.ok/err/info/warn`，自动消失 |
| `src/components/ui/UiToaster.vue` | 渲染队列，`Teleport` 到 body |
| `ui/index.ts` / `App.vue` | 导出原语 + 挂载 `<UiToaster />` |

**迁移 8 个 console 组件**（`Conversation` / `EnvView` / `History` / `MemoryView` / `ScheduleView` / `Status` / `TaskView` / `Tools`）加 `ConsoleSettings`：

- **加载类**（拉取列表/详情失败）→ `useAsync` + `<UiErrorNote/>`
- **操作类**（保存 / 删除 / 新增 Profile / 检测连接 / 设密钥）→ `notify.ok` / `notify.err`
- **消除字符串嗅探**：删除 `ConsoleSettings.isErr()`（现靠 `m.includes('失败') || m.includes('无效')` 判断是否标红），`msg` 字符串改为类型化 toast 调用
- **统一文案标点**：现混用半角 `'加载失败: '`（`ConsoleTools.vue`）与全角 `'加载失败：'`（其余），统一为全角

## 测试策略

**TDD 覆盖（先写失败测试）**

- 后端 2a：`tests/test_orchestrator_pipeline.py` 新增用例——把 `extract_and_store` patch 为「置位 Event 后挂起」，断言 `run_pipeline` 返回后 `_bg_tasks` 非空、释放后归空。旧代码无该集合，测试必然先失败。
- 前端 `errors.spec.ts`：`formatError` 对 `Error` / `string` / `undefined` / 任意对象的输出。
- 前端 `useAsync.spec.ts`：成功取 `data`、失败取 `error` 且 `loading` 复位、再次 `run` 会先清空上一次的 `error` 再覆盖 `data`。
- 前端 `useToast.spec.ts`：入队/自动消失/多类型（用 `vi.useFakeTimers`）。纯逻辑，现有 node 测试环境即可，无需 jsdom。

**全量回归**

- 后端：`python -m pytest tests/ -q`、`python -m mypy core/ server.py`
- 前端：`npm test`、`npm run build`（`vue-tsc` 类型检查 + vite 构建）

## 风险与验证缺口

| 风险 | 处置 |
|---|---|
| **组件迁移无自动化测试** | 无 `jsdom` / `@vue/test-utils`，`.vue` 改动只能靠 `vue-tsc` + 构建 + **手动跑页面**验证。这是本次唯一未被测试覆盖的部分，不以"测试通过"含糊表述 |
| CSS 拆分导致视觉回归 | `cs-*` 规则按边界搬运，人工比对设置页各模块（LLM / ASR / TTS / 语音 / 高级）渲染 |
| 单例 state 陈旧 | 保留 `onMounted` 重新 `load()` |
| toast 新 UI 面影响既有布局 | `Teleport` 到 body，不参与页面流式布局；`z-index` 需高于悬浮球面板 |
| 迁移面广（9 个 .vue） | 按组件逐个提交，每个组件迁移后即跑 `npm run build`，避免一次性大改难以定位回归 |

## 不做（明确排除）

- 不修 2b（复核为非缺陷）
- 不改后端 API 契约与 `response_model`
- 不引入 `jsdom` / `@vue/test-utils` 组件测试基建
- 不动确认层解析（已由 `fd61203` 修复，其残留的犹豫句式误判问题另项处理）
