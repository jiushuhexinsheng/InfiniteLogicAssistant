# 大模型设置页重构 + 对话内全局模型切换器 — 设计

- 日期：2026-10-24
- 范围：`web/src/components/console/settings/`（LLM 页）、`web/src/components/assistant/ChatInput.vue`、
  `core/api/`（新增两个只读/写入端点）
- 状态：待批准

## 1. 背景与问题

「大模型」设置页当前由 `ModelProviderPanel.vue`（供应商列表 + 两步向导）和
`ServiceCard.vue`（当前 Profile 字段 + 高级兼容）组成。用户提出 7 条问题：

1. 供应商列表里删除是右下角的 `×`，不明显；一行内名称/协议/地址/Key/当前标记挤在一起。
2. 新增供应商向导第 1 步「下一步」填完仍不可点。
   **已复现根因**：`step1Valid` 要求 ID 满足小写正则、URL 带 `http(s)://`、且 ID 不与现有
   profile 重名。任何一条不满足时按钮只是**静默禁用**，界面没有说明。实测：填
   `Provider ID=openai`（已存在）+ 合法 URL → 按钮保持禁用，无任何提示。
3. 第 2 步的模型列表是「标签墙」（`span` 圆角标签），不能逐条修改。
4. 「获取模型」结果直接塞进标签墙；添加模型的输入框是普通文本框，不是可选可输。
5. 模型「配置」与「当前使用」混在一起：设置页里既有 Profile 选择又有模型输入；希望
   在对话输入框旁有一个全局模型切换器，设置页只负责配置。
6. 测试连接成功后只有 toast，按钮旁没有持续可见的状态点。
7. 「高级兼容」上方的快捷 chip 占一排；希望删掉 chip，把内置键变成兼容**键输入框**的
   可选项（可输入、可选择，一个组件）。

另外：项目要求**能抽组件的一律抽组件**，页面只做组合。

## 2. 目标 / 非目标

### 目标

- 供应商列表可读、删除显式可控、可编辑已有供应商。
- 向导每一步给出**为什么不能继续**的即时提示；不再静默禁用。
- 模型列表升级为可编辑表格；拉取结果以列表形式供挑选；模型输入用组合框。
- 「当前助手使用哪个模型」= 对话输入框旁的全局切换器（按供应商分组），切换即持久化。
- 测试连接结果在按钮旁以小圆点持续显示。
- 高级兼容去掉快捷 chip，键列改为组合框（内置键为选项，选中自动带出默认值）。
- 组件化拆分，页面文件只做布局与数据装配。

### 非目标

- 不改动 `config.yaml` 的 schema 字段（`profiles[].model` / `profiles[].models` /
  `llm.active` 已足够）。
- 不做按会话独立模型（用户已确认：**全局**）。
- 不重做语音页的引擎/本地模型/唤醒等区块，只替换其中复用的供应商配置组件。
- 不做供应商模型目录自动发现（仍以「获取模型」按钮为准）。

## 3. 交互设计

### 3.1 供应商列表（`ProviderList.vue` + `ProviderRow.vue`）

每行：

```
[名称 / ID]  [协议徽章]  [模型数·Key 状态]        [当前] [编辑] [删除]
endpoint（等宽小字，超长省略）
```

- 整行点击 = **编辑**（打开向导并预填；ID 只读，见 3.2）。
- 「当前」是徽章，不承担点击切换职责（切换在对话里；设置页仍保留 Profile 下拉作为
  兼容入口——见 3.5）。
- 删除 = 独立的 `UiButton variant="danger"` 图标/文字按钮，点击弹确认对话框
  （`ConfirmDialog.vue`，基于 `UiModal`）：说明会删除该供应商及其模型与密钥，主按钮
  「删除」，次按钮「取消」。
- 模型数 = `models` 与当前 `model` 的并集去重后的数量（修掉「0 模型」误导）。
- Key 状态用 `UiChip`/`UiStatusDot` 表达「已设置 / 未设置」。
- 空列表时展示引导文案与「新增供应商」。

### 3.2 新增 / 编辑向导（`ProviderWizard.vue`）

模态框，两步。编辑模式与新增共用，标题区分「新增供应商 / 编辑供应商」。

**第 1 步：身份**

- 内置供应商卡片（OpenAI / DeepSeek / Anthropic / Xiaomi MiMo）仍可一键预填。
- 字段：Provider ID、协议、Base URL。
- 校验提示（字段下方常驻，不在提交时才出现）：
  - ID 非法：`只能小写字母/数字/-/_，且以字母或数字开头`
  - ID 已存在：`该 ID 已被使用——从左侧列表点击它进入编辑` （**不再只是禁用**）
  - URL 非法：`需要以 http:// 或 https:// 开头`
- 「下一步」在非法时禁用，并在按钮旁显示第一条错误摘要；合法时立即可点。
- 编辑模式：ID 输入禁用（避免改名牵连 secrets 与引用），其余字段可改。

**第 2 步：连接与模型**

- API Key：只写不读；显示「已设置 / 未设置」；「设置密钥」走现有 `ApiKeyModal` 或内联
  输入（保存时 `PUT /api/config/secrets`）。
- 「获取模型」按钮右侧显示结果：成功 → `已获取 N 个模型`；失败 → 错误文案 + 可手动输入。
- **拉取结果列表**（`FetchedModelList.vue`）：可滚动复选列表，带「全选 / 反选 / 添加所选」；
  已添加的条目标记「已添加」并禁用勾选。
- **模型表格**（`ModelTable.vue`）：一行一个模型
  - 第 1 列：`UiCombobox`（可输入可选，选项 = 已拉取模型 ∪ 当前表格内模型），编辑即改该行；
  - 第 2 列：删除按钮；
  - 底部：「＋ 添加模型」新增空行（自动聚焦），或从拉取列表批量添加。
  - 空表格允许，但保存时提示至少一个模型（按钮禁用 + 说明）。
- 保存：写 `profiles[id] = { provider, endpoint, chat_path, model, models, ... }`；
  三段统一保留各自的专有字段：ASR 的 `language`、TTS 的 `format` / `voice` / `voices` /
  `voice_ref`，以及三段共有的 `compat` / `timeout` 等未在向导中编辑的字段（编辑模式先
  复制原 profile 再覆盖向导字段）。
- **编辑模式预填 = `models` ∪ 当前 `model`**（去重保序）；保存时若旧 `model` 仍在表格中
  就保留它，否则回落到第一行。
- 新增供应商是否设为 active：**只有在一份 profile 都没有时**才自动设为 active；已有
  profile（即使 `llm.active` 是空串、运行时回落到第一个）时不改变全局选择。

### 3.3 测试连接状态点（`DetectionStatusDot.vue`）

- 位置：`ServiceCard` 卡头「测试连接」按钮的左侧。
- 状态：未测（灰）/ 测试中（品牌色脉冲）/ 成功（绿）/ 失败（红）。
- 数据源：`connResults[section.name]`（已有）；toast 保留。
- 复用 `UiStatusDot`，只封装状态映射与标题（如「上次检测：成功 · 120ms」）。

### 3.4 高级兼容（`CompatEditor.vue`）

- 删除 `COMPAT_SHORTCUTS` 的 chip 行。
- 键列改为 `UiCombobox`，选项 = `COMPAT_SHORTCUTS` 的 key（如 `auth_header`）；选中某个
  内置键时自动把值填为对应默认值（仍可手改）；也可输入任意自定义键。
- 值列保持 `UiInput`；删除按钮保留。
- 「＋ 新增兼容键」新增空行。
- 行组件 `CompatRow.vue`，编辑器 `CompatEditor.vue` 管理增删改。

### 3.5 模型「配置」与「选择」分离

设置页（LLM / ASR / TTS 三段统一）只保留**配置**：

- 供应商与模型列表（3.1–3.2）。
- `ServiceCard` 的 `fields` 中**三段都去掉 `model`**；模型统一由向导的模型表格维护，
  「获取模型」只保留向导内一处（删除卡片里的第二个写入口）。
- API Key 状态行保留（`ApiKeyModal` 已挂在 `ConsoleSettings` 根节点，语音页复用同一个）。
- Profile 下拉改为**本地「编辑对象」选择器**：只决定卡片正在编辑哪个 profile，
  **不写 `llm.active`**（避免编辑动作改变运行时选择）。默认值是解析后的 active
  （空串 → 第一个 profile）。
- 需要真正切换全局供应商时，供应商行提供显式「设为当前」动作（与对话切换器等效）。

对话侧新增**全局模型切换器**：

- 位置：`ChatInput.vue` 的输入行最左侧，紧凑触发器（当前模型名，超长省略 + chevron）。
- 组件：`ModelPicker.vue`（业务） + `UiGroupedSelect.vue`（通用分组下拉）。
- 分组：每个 LLM profile 一组，组头显示供应商名/ID；组内列出该供应商的模型
  （`models` ∪ 当前 `model`，去重）。当前项打勾。
- 顶部搜索框（按模型名/供应商名过滤）；键盘 ↑↓/Enter/Esc 可用。
- 选择即**全局**生效：`POST /api/llm/active-model {provider, model}`；成功后刷新配置并
  更新触发器；失败 toast + 保持原选择。
- 未配置任何 LLM profile 时，触发器显示「未配置模型」并禁用，点击打开设置页引导文案。

## 4. 后端契约（新增，改动最小）

### 4.0 `/api/config` 增加 `llm_model`

顶栏 `NavSystemInfo.vue` 目前显示 `llm_profile`（只有供应商名），同一供应商内切换模型时
不会变化。给 `ConfigResponse` 增加 `llm_model: str = ""`，`core/api/voice/meta.py` 用
`resolve_llm_profile()` 解析出的 profile 的 `model` 填充；顶栏显示
`llm_model || llm_profile || 未配置`。`ConsoleStatus` / 启动页保持原样（供应商名）。


### 4.1 `GET /api/llm/models`

返回分组模型清单，供对话切换器使用：

```json
{
  "ok": true,
  "active": {"provider": "xiaomi-mimo-llm", "model": "mimo-v2.6-pro"},
  "groups": [
    {"provider": "deepseek", "label": "deepseek",
     "models": ["deepseek-chat", "deepseek-reasoner"],
     "current_model": "deepseek-chat"}
  ]
}
```

- `models` = 该 profile `models` 列表与 `model` 的并集（去重、保序）。
- 不返回任何密钥；直接读 `config.settings`。

### 4.2 `POST /api/llm/active-model`

请求 `{"provider": "...", "model": "..."}`；校验 provider 存在、model 非空且属于该
provider 的模型集合（或允许任意非空？——**决定：必须属于该 provider 的 `models` ∪ 当前
`model`**，防止误写）；写入 `llm.active=provider`、`profiles[provider].model=model`，
`reload_settings(source="api.llm_model")`，返回 `{ok, active}`。

- 采用专用端点而非 `PATCH /api/config`：后者对 `profiles` 段是**整份替换**
  （`_wholesale_profiles`），聊天侧只发一个模型时会把其余 profile 全部删掉。
- 测试：provider 不存在 400、model 不在集合 400、正常写入并热重载。

## 5. 组件拆分清单

| 组件 | 位置 | 职责 |
|---|---|---|
| `ProviderList.vue` | settings/ | 列表容器、空态、新增入口 |
| `ProviderRow.vue` | settings/ | 单行展示 + 编辑/删除动作 |
| `ProviderWizard.vue` | settings/ | 新增/编辑两步向导（组合下列子组件） |
| `ModelTable.vue` | settings/ | 可编辑模型表格 |
| `FetchedModelList.vue` | settings/ | 拉取结果复选列表 |
| `CompatEditor.vue` / `CompatRow.vue` | settings/ | 高级兼容键值编辑 |
| `DetectionStatusDot.vue` | settings/ | 测试连接状态点 |
| `ConfirmDialog.vue` | ui/ | 通用确认对话框（删除供应商等） |
| `ModelPicker.vue` | assistant/ | 对话内模型切换器（触发器 + 数据） |
| `UiGroupedSelect.vue` | ui/ | 通用分组下拉（搜索/键盘/分组标题） |

页面组合：`ConsoleSettings.vue` → `ModelProviderPanel.vue` 退化为薄容器（`ProviderList`
+ `ProviderWizard`），`ServiceCard.vue` 仅保留字段表单，抽出兼容编辑器与状态点。

## 6. 数据流

- 设置页读取 `GET /api/config/full`（既有 `editable_snapshot`），保存走 `PATCH /api/config`
  （既有 `moduleBody`）。
- 拉取模型走 `POST /api/providers/fetch-models`（既有）。
- 对话切换器读取 `GET /api/llm/models`；切换走 `POST /api/llm/active-model`。
- 切换成功后：刷新 `/api/config`（顶栏「当前 LLM 模型」也同步）与本地切换器状态。

## 7. 边界与错误

- 删除当前 active 供应商：保存后 active 回落到剩余第一个；若一个不剩，`active=""`，
  对话切换器显示「未配置模型」。
- **`active=""` 的语义统一为「运行时取第一个 profile」**：供应商行「当前」徽章、
  `ModelPicker` 初始选中、ServiceCard 的编辑对象都先解析空串 → 第一个 profile；只有
  一个 profile 都没有时才显示「未配置」。
- **删除供应商同时清理密钥**：先 `PATCH /api/config` 移除 profile（失败则中止），再
  `PUT /api/config/secrets` 写入空值清除 `<section>.profiles.<id>`。清理失败只提示
  「配置已删除，但密钥清理失败」，不回滚配置；ASR/TTS 同样处理。
- 编辑模式不允许改 ID（改名会留下旧 secrets 条目与历史引用）。
- 拉取模型失败不清空已配置表格。
- 模型 ID 去重：trim 后大小写敏感比较。
- 切换模型时后端校验失败 → toast，触发器回滚到旧值。
- 小屏/窄面板：触发器只显示模型名（省略号），下拉面板最大高度受限、可滚动。

## 8. 测试

前端（vitest）：

- `ProviderWizard`：ID 非法 / 重名 / URL 非法时显示对应提示且 Next 禁用；合法时启用；
  编辑模式 ID 只读；保存保留 `compat`/`voices` 与旧 `model`。
- `ModelTable`：增行、改行、删行、去重、空表提示。
- `FetchedModelList`：已添加项禁用、全选/反选、添加所选。
- `ModelPicker`：按供应商分组、当前项勾选、搜索过滤、选择后调用端点并刷新。
- `DetectionStatusDot`：四种状态映射。
- `CompatEditor`：选内置键自动带值、手输键保留、删行。
- `ChatInput` 集成：切换器渲染与禁用态。

后端（pytest）：

- `GET /api/llm/models` 分组与并集正确、无密钥。
- `POST /api/llm/active-model` 正常写入 + 热重载来源、未知 provider/model 400。
- 保持 `gen:api` 同步（新增 response model → `npm run gen:api`）。

手工验收（Playwright）：新增供应商全流程、编辑、删除确认、拉取模型、切换模型后顶栏与
对话一致、测试连接绿点、兼容键组合框。

## 9. 已确认 / 我的判断

- **范围：LLM / ASR / TTS 三段一起改**（用户已确认）。共用组件不再按 section 分支保留
  旧行为；向导保存保留各段专有字段（ASR `language`；TTS `format`/`voice`/`voices`/
  `voice_ref`）。`ApiKeyModal` 挂在 `ConsoleSettings` 根节点，语音页（其子组件）复用同一
  实例，无需新挂载。
- 第 7 条：快捷 chip 删除后，兼容**键**输入框变为 combobox，内置键作为选项并在选中时
  自动填默认值。（若你原意是 API Key 框也要可输可选，请指出——本设计按兼容键列理解。）
- 第 5 条「模型的具体参数页」按 LLM 设置页的 Profile 参数卡理解；模型参数（max_tokens /
  temperature 等）仍按 profile 配置，不随模型单独存。
- 顶栏同步通过 `/api/config` 新增 `llm_model` 实现（见 4.0）。
- `ServiceCard` 三段都删除 `model` 字段与「获取模型」按钮；模型只有一个写入口（向导
  的模型表格）。API Key 行保留；Profile 下拉降级为本地「编辑对象」，不写 `active`。
- 编辑供应商的模型表格预填 `models ∪ model`；保存时旧 `model` 仍在表中则保留。
