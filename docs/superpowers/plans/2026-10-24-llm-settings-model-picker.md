# 大模型设置页重构 + 对话内全局模型切换器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 LLM/ASR/TTS 的供应商配置重做为可编辑、可校验、组件化的界面，并在对话输入框旁加入按供应商分组的全局模型切换器。

**Architecture:** 后端新增两个小端点（分组模型清单、设置全局 active 模型）并给 `/api/config` 补 `llm_model`；前端先抽出通用 UI 组件（分组下拉、确认框），再拆设置域业务组件（列表/行/向导/模型表格/拉取列表/兼容编辑器/状态点），最后组装页面并把 `ModelPicker` 挂进 `ChatInput`。

**Tech Stack:** FastAPI + pydantic（Python 3.14）、Vue 3 + TypeScript + Vite、vitest、pytest。

**Spec:** `docs/superpowers/specs/2026-10-24-llm-settings-model-picker-design.md`

## Global Constraints

- 三段（`llm` / `asr` / `tts`）共用新组件，不保留两套旧 UI。
- 组件化：页面只做组合；能复用的控件先抽 `ui/`，业务组件放 `settings/` 或 `assistant/`。
- 任何后端 schema 改动后必须运行 `cd web && npm run gen:api` 并提交 `generated.ts`。
- 密钥永不回显；删除供应商时同步清理 secrets。
- 所有新 UI 文案中文为主，沿用现有英文副标题风格。
- 不新增第三方依赖。
- 每个任务先写失败测试、确认失败原因，再实现转绿；提交前跑任务相关测试。

## Review Focus

1. 删除供应商后复用同一 ID：旧密钥不得「复活」（secrets 清理有测试）。
2. 编辑已有供应商：当前 `model`、`compat`、`voices` 等未被向导编辑的字段必须保留。
3. 对话内切换模型：不得经 `PATCH /api/config` 的 `profiles` 整段替换删掉其他供应商。
4. `active` 为空串：列表徽章、切换器选中、运行时解析必须一致指向第一个 profile。
5. 向导非法输入：Next 禁用时必须给出具体原因，不能静默。

---

### Task 1: 后端分组模型清单 + `/api/config.llm_model`

**Files:**
- Create: `core/api/schemas/llm.py`
- Create: `core/api/llm.py`
- Modify: `core/api/schemas/__init__.py`
- Modify: `core/api/schemas/voice.py`（`ConfigResponse` 增加 `llm_model`）
- Modify: `core/api/voice/meta.py`
- Modify: `server.py`（挂载 llm router）
- Test: `tests/server/test_server_llm_models.py`

**Interfaces:**
- Consumes: `core.config.resolve_llm_profile() -> (name, profile_dict)`。
- Produces:
  - `GET /api/llm/models` → `{"ok": true, "active": {"provider": str, "model": str}, "groups": [{"provider": str, "label": str, "models": list[str], "current_model": str}]}`
  - `ConfigResponse.llm_model: str`（默认为 `""`）

- [ ] **Step 1: 写失败测试** `tests/server/test_server_llm_models.py`

```python
def test_llm_models_groups_union_and_active(client, monkeypatch):
    """models 与当前 model 去重合并；active 为空串时解析到第一个 profile。"""
    ...  # 用 monkeypatch 替换 config.settings.llm 为带两个 profile 的 LlmSection
    r = client.get("/api/llm/models")
    assert r.status_code == 200
    body = r.json()
    assert body["active"]["provider"] == "p1"
    assert [g["provider"] for g in body["groups"]] == ["p1", "p2"]
    assert body["groups"][0]["models"] == ["m1", "m-only"]
    assert "api_key" not in r.text
```

- [ ] **Step 2: 运行确认失败**：`python -m pytest tests/server/test_server_llm_models.py -q` → 404。

- [ ] **Step 3: 实现** `core/api/schemas/llm.py`（`LlmActive` / `LlmModelGroup` / `LlmModelsResponse(ApiResponse)`）、`core/api/llm.py` 路由；`server.py` 与 `core/api/schemas/__init__.py` 接线。模型集合 = `set(profile.models) | {profile.model}` 去空、保序；`active = llm.active or 第一个 profile`。

- [ ] **Step 4: 运行确认通过**：同一命令 → PASS。

- [ ] **Step 5: 写 `/api/config.llm_model` 失败测试**（`tests/server/test_server_basic.py` 或新文件）：`client.get("/api/config").json()["llm_model"] == "m1"`。

- [ ] **Step 6: 实现并转绿**：`ConfigResponse.llm_model: str = ""`；`meta.py` 用 `resolve_llm_profile()[1].get("model", "")` 填充。

- [ ] **Step 7: 重新生成前端类型**：`cd web && npm run gen:api`。

- [ ] **Step 8: 提交**

```bash
git add core/api/schemas/llm.py core/api/llm.py core/api/schemas/__init__.py \
  core/api/schemas/voice.py core/api/voice/meta.py server.py \
  tests/server/test_server_llm_models.py web/src/api/generated.ts
git commit -m "feat(api): 分组模型清单与 /api/config.llm_model"
```

---

### Task 2: 后端设置全局 active 模型

**Files:**
- Modify: `core/api/llm.py`
- Test: `tests/server/test_server_llm_models.py`

**Interfaces:**
- Produces: `POST /api/llm/active-model` body `{"provider": str, "model": str}` →
  `{"ok": true, "active": {"provider": str, "model": str}, "error": null}`；
  未知 provider 或 model 不属于该 provider 的模型集合 → 400 `{"ok": false, "error": "..."}`。

- [ ] **Step 1: 写失败测试**

```python
def test_set_active_model_persists_and_reloads(client, monkeypatch):
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.yaml")
    ...  # 先写一份最小合法 config.yaml
    r = client.post("/api/llm/active-model", json={"provider": "p2", "model": "m2"})
    assert r.status_code == 200 and r.json()["active"] == {"provider": "p2", "model": "m2"}
    assert yaml.safe_load(...)["llm"]["profiles"]["p2"]["model"] == "m2"

def test_set_active_model_rejects_unknown_provider_or_model(client):
    assert client.post(..., json={"provider": "nope", "model": "m"}).status_code == 400
    assert client.post(..., json={"provider": "p1", "model": "not-listed"}).status_code == 400
```

- [ ] **Step 2: 运行确认失败**（404）。

- [ ] **Step 3: 实现**：读 `CONFIG_FILE` → 校验 provider/model（允许集合同 Task 1）→ 写 `llm.active` 与 `profiles[provider].model` → `Settings(**data)` 校验 → 写回 YAML → `reload_settings(source="api.llm_model")`。**不要**走 `PATCH /api/config`（会整段替换 profiles）。测试中断言「设置 p2 后 p1 profile 仍在文件中」。

- [ ] **Step 4: 运行确认通过**。

- [ ] **Step 5: 提交**

```bash
git add core/api/llm.py tests/server/test_server_llm_models.py
git commit -m "feat(api): POST /api/llm/active-model 设置全局模型"
```

---

### Task 3: 通用分组下拉 `UiGroupedSelect`

**Files:**
- Create: `web/src/components/ui/UiGroupedSelect.vue`
- Modify: `web/src/components/ui/index.ts`
- Test: `web/src/components/ui/__tests__/UiGroupedSelect.spec.ts`

**Interfaces:**
- Produces:
```ts
export interface GroupedOption { value: string; label: string; disabled?: boolean }
export interface OptionGroup { label: string; options: GroupedOption[] }
// props: groups: OptionGroup[]; modelValue: string; placeholder?: string;
//        disabled?: boolean; searchable?: boolean (default true)
// emits: 'update:modelValue' (string)
```
- 行为：触发器显示当前选中项的 label；面板按组渲染组标题；搜索框按 label 过滤（空组隐藏）；
  ↑↓ 跨组移动、Enter 选中、Esc 关闭、外点关闭；复用 `useAnchoredPanel`。

- [ ] **Step 1: 写失败测试**：渲染两组，断言组标题顺序；点击选项 emit 正确 value；输入过滤词后只剩匹配项；Esc 关闭。
- [ ] **Step 2: 运行** `npx vitest run src/components/ui/__tests__/UiGroupedSelect.spec.ts` → 组件不存在/失败。
- [ ] **Step 3: 实现**（面板自己渲染，`id=listId` 以配合 `useAnchoredPanel`；不改造 `UiPopoverPanel`）。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**

```bash
git add web/src/components/ui/UiGroupedSelect.vue web/src/components/ui/index.ts \
  web/src/components/ui/__tests__/UiGroupedSelect.spec.ts
git commit -m "feat(ui): 可搜索的分组下拉 UiGroupedSelect"
```

---

### Task 4: 通用确认对话框 `ConfirmDialog`

**Files:**
- Create: `web/src/components/ui/ConfirmDialog.vue`
- Modify: `web/src/components/ui/index.ts`
- Test: `web/src/components/ui/__tests__/ConfirmDialog.spec.ts`

**Interfaces:**
```ts
// props: modelValue: boolean; title: string; message: string;
//        confirmText?: string ('确认'); cancelText?: string ('取消'); danger?: boolean
// emits: 'update:modelValue' (boolean), 'confirm' (), 'cancel' ()
```

- [ ] **Step 1: 失败测试**：打开时显示标题/正文；点取消 emit cancel + 关闭；点确认 emit confirm + 关闭。
- [ ] **Step 2: 运行确认失败**。
- [ ] **Step 3: 实现**（基于 `UiModal` + `UiButton variant="danger"`）。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 5: 测试连接状态点 `DetectionStatusDot`

**Files:**
- Create: `web/src/components/console/settings/DetectionStatusDot.vue`
- Test: `web/src/components/console/settings/__tests__/DetectionStatusDot.spec.ts`

**Interfaces:**
```ts
// props: status: 'idle' | 'testing' | 'ok' | 'fail'; detail?: string
// 纯展示：由调用方从 connResults / detecting 派生 status
```
映射：idle 灰 / testing 品牌色脉冲 / ok 绿 / fail 红；`title` 使用 `detail`。

- [ ] **Step 1: 写失败测试**：四种状态分别渲染对应 tone 的 `UiStatusDot`（用 class 或 aria-label 断言），title 含 detail。
- [ ] **Step 2: 运行确认失败**：`npx vitest run src/components/console/settings/__tests__/DetectionStatusDot.spec.ts`。
- [ ] **Step 3: 实现**（复用 `UiStatusDot` 与现有 `detection.ts` 的类型）。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 6: 可编辑模型表格 `ModelTable`

**Files:**
- Create: `web/src/components/console/settings/ModelTable.vue`
- Test: `web/src/components/console/settings/__tests__/ModelTable.spec.ts`

**Interfaces:**
```ts
// props: models: string[]; options: string[]（combobox 候选）
// emits: 'update:models' (string[])
```
行为：每行一个 `UiCombobox`（可输可选）；行删除；「＋ 添加模型」追加空行并聚焦；
输入 trim、去重（大小写敏感）、空行不写入提交值。

- [ ] **Step 1: 写失败测试**：三行 → 改第二行 emit 新数组；删行；添加行；重复值被忽略；空行被过滤。
- [ ] **Step 2: 运行确认失败**：`npx vitest run src/components/console/settings/__tests__/ModelTable.spec.ts`。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 7: 拉取结果列表 `FetchedModelList`

**Files:**
- Create: `web/src/components/console/settings/FetchedModelList.vue`
- Test: `web/src/components/console/settings/__tests__/FetchedModelList.spec.ts`

**Interfaces:**
```ts
// props: models: string[]; added: string[]
// emits: 'add' (picked: string[])
```
行为：复选列表；已添加项禁用并显示「已添加」；全选/反选（只作用于未添加项）；「添加所选」emit。

- [ ] **Step 1: 写失败测试**（勾选两项 → add 收到两项；已添加不可勾选；反选只作用于未添加项）。
- [ ] **Step 2: 运行确认失败**：`npx vitest run src/components/console/settings/__tests__/FetchedModelList.spec.ts`。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 8: 供应商行与列表 `ProviderRow` / `ProviderList`

**Files:**
- Create: `web/src/components/console/settings/ProviderRow.vue`
- Create: `web/src/components/console/settings/ProviderList.vue`
- Test: `web/src/components/console/settings/__tests__/ProviderList.spec.ts`

**Interfaces:**
```ts
export interface ProviderSummary {
  id: string; name: string; protocol: string; endpoint: string
  keySet: boolean; active: boolean; modelCount: number
}
// ProviderRow props: provider: ProviderSummary
//   emits: edit(), remove(), activate()
// ProviderList props: providers: ProviderSummary[]
//   emits: add(), edit(id), remove(id), activate(id)
```
列表负责删除确认（`ConfirmDialog`）；行内「删除」是独立 `danger` 按钮；整行点击 = edit；
非 active 行显示「设为当前」。`modelCount` 由调用方按 `models ∪ model` 计算。

- [ ] **Step 1: 写失败测试**：渲染两行、名称/地址/Key/当前徽章；点行 emit edit；点删除先弹确认、确认后 emit remove；点「设为当前」emit activate。
- [ ] **Step 2: 运行确认失败**：`npx vitest run src/components/console/settings/__tests__/ProviderList.spec.ts`。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 9: 向导第 1 步（身份 + 校验）

**Files:**
- Create: `web/src/components/console/settings/ProviderWizard.vue`
- Test: `web/src/components/console/settings/__tests__/ProviderWizard.spec.ts`

**Interfaces:**
```ts
// props: modelValue: boolean; section: 'llm'|'asr'|'tts';
//        editingId?: string | null; profiles: Record<string, ProfileConfig>
// emits: 'update:modelValue', 'saved'(id: string), 'close'
```
第 1 步字段：Provider ID / 协议 / Base URL。校验消息（常驻字段下方）：
`ID 只能小写字母/数字/-/_`；`该 ID 已被使用——从列表点击进入编辑`；`URL 需以 http:// 或 https:// 开头`。
Next 在非法时禁用，并在按钮旁显示第一条错误。编辑模式 ID disabled。预设卡片仍可一键预填并进入第 2 步。

- [ ] **Step 1: 写失败测试**：非法 ID → 显示对应文案且 Next disabled；重名 → 显示重名文案；合法 → Next enabled；编辑模式 ID disabled。
- [ ] **Step 2: 运行确认失败**：`npx vitest run src/components/console/settings/__tests__/ProviderWizard.spec.ts`。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 10: 向导第 2 步（密钥 / 拉取 / 模型表格 / 保存）

**Files:**
- Modify: `web/src/components/console/settings/ProviderWizard.vue`
- Test: `web/src/components/console/settings/__tests__/ProviderWizard.spec.ts`

**Interfaces:**
- Consumes: `ModelTable`、`FetchedModelList`（Task 6/7）；`api.fetchModels`、`api.putSecret`。
- Produces: 保存时 emit `saved(id)` 并关闭；`profile` 负载：
  `{ provider, endpoint, chat_path, model, models, ...preserved }`。

- [ ] **Step 1: 失败测试**
  - 拉取成功 → 渲染列表；添加所选进入表格。
  - 保存新供应商 → `api.fetchModels` 未被用于保存；`api.putSecret` 仅在填了 key 时调用；payload 的 `model = models[0]`。
  - 编辑已有 profile（含 `compat`、`voices`、`language`/`format`）→ 保存 payload 保留这些字段；旧 `model` 若仍在表格中则保持。
  - 预填 = `models ∪ model`。
  - 拉取失败 → 错误文案出现，已配置的表格内容不变。
- [ ] **Step 2: 运行确认失败**：同一 vitest 文件。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 11: 兼容编辑器 `CompatEditor` / `CompatRow`

**Files:**
- Create: `web/src/components/console/settings/CompatEditor.vue`
- Create: `web/src/components/console/settings/CompatRow.vue`
- Test: `web/src/components/console/settings/__tests__/CompatEditor.spec.ts`

**Interfaces:**
```ts
// props: entries: Array<[string, string]>
// emits: 'update' (entries: Array<[string, string]>)
```
键列 `UiCombobox`，选项 = `COMPAT_SHORTCUTS` 的 key；选中内置键自动填默认 value；
手输任意键保留；值列 `UiInput`；删除行；「＋ 新增兼容键」。不再渲染快捷 chip。

- [ ] **Step 1: 写失败测试**（选 `auth_header` → 值自动为 `api-key`；手输键不清值；删行；不再渲染快捷 chip）。
- [ ] **Step 2: 运行确认失败**：`npx vitest run src/components/console/settings/__tests__/CompatEditor.spec.ts`。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 12: `ServiceCard` 收缩 + 页面组装（三段）

**Files:**
- Modify: `web/src/components/console/settings/ServiceCard.vue`
- Modify: `web/src/components/console/settings/ModelProviderPanel.vue`（退化为 `ProviderList + ProviderWizard`）
- Modify: `web/src/components/console/settings/configDefs.ts`（三段 `fields` 去掉 `model`）
- Modify: `web/src/components/console/settings/profiles.ts`（删除 `toggleCompat` 等只服务于 chip 的逻辑）
- Test: `web/src/components/console/settings/__tests__/ConsoleSettings.spec.ts`、`ServiceCard.spec.ts`

**Interfaces:**
- `ServiceCard` 不再渲染 `model` 输入与「获取模型」；Profile 下拉改为本地 `editTarget`（不写 `active`）；卡头加入 `DetectionStatusDot`。
- `ModelProviderPanel` 组合 `ProviderList` + `ProviderWizard`，删除逻辑 = 移除 profile + `putSecret(...,'')` 清密钥（失败仅提示）。
- 「设为当前」= 写 `active` 并保存。

- [ ] **Step 1: 写失败测试**：LLM 卡不渲染模型输入/获取模型按钮；状态点随 `connResults` 变化；ProviderList 删除会先调 `patchConfig` 再 `putSecret(...,'')`；三段的 fields 均不含 `model`。
- [ ] **Step 2: 运行确认失败**：`npx vitest run src/components/console/settings/__tests__/ConsoleSettings.spec.ts`。
- [ ] **Step 3: 实现**（同步更新受影响的既有测试夹具）。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 13: 对话内 `ModelPicker` + ChatInput + 顶栏

**Files:**
- Create: `web/src/components/assistant/ModelPicker.vue`
- Modify: `web/src/components/assistant/ChatInput.vue`
- Modify: `web/src/components/layout/NavSystemInfo.vue`
- Modify: `web/src/api/endpoints.ts`
- Test: `web/src/components/assistant/__tests__/ModelPicker.spec.ts`、`ChatInput.spec.ts`

**Interfaces:**
- `api.getLlmModels()` → `LlmModelsResponse`；`api.setActiveModel(provider, model)` → `SetActiveModelResponse`。
- `ModelPicker` 无 props：打开时拉取清单；触发器显示当前模型名；选项 value 为 `${provider}\u0000${model}`；选择后调用 `setActiveModel`，成功刷新 `useConfig()`，失败 toast 并回滚。
- `ChatInput` 在 `.chat-input-row` 最左渲染 `<ModelPicker />`。
- `NavSystemInfo` 显示 `llm_model || llm_profile || '未配置'`。

- [ ] **Step 1: 失败测试**
  - 拉取两个 provider 的模型 → 组标题与模型项正确；当前项勾选。
  - 选择另一项 → `setActiveModel(provider, model)` 被调用；失败时触发 toast 且选中不变。
  - ChatInput 渲染 picker；无 profile 时触发器禁用并显示「未配置模型」。
  - Nav 显示模型名优先。
- [ ] **Step 2: 运行确认失败**：`npx vitest run src/components/assistant/__tests__/ModelPicker.spec.ts`。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 运行确认通过**。
- [ ] **Step 5: 提交**。

---

### Task 14: 文档、类型同步与全量验证

**Files:**
- Modify: `README.md`、`wiki/API.md`、`wiki/Configuration.md`（新增端点与 llm_model）
- Verify: `web/src/api/generated.ts` 已同步

- [ ] **Step 1: 更新文档**：README API 表补两条；wiki/API 补两条；说明设置页与对话切换器分工。
- [ ] **Step 2: 全量验证**

```bash
cd web && npm run gen:api && npm run build && npm test
cd .. && python -m pytest tests/ -q && python -m mypy core/ server.py && python -m ruff check core/ server.py main.py cli/
```

- [ ] **Step 3: 手工验收（Playwright）**：新增/编辑/删除供应商、删除确认、拉取模型并添加、切换模型后顶栏与对话一致、绿点、兼容键组合框。截图存档。
- [ ] **Step 4: 提交**

```bash
git add README.md wiki/API.md wiki/Configuration.md
git commit -m "docs: 记录模型切换端点与设置页新分工"
```
