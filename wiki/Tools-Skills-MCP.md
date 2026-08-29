# 工具 / Skills / MCP

## @tool 注册中心

工具由后端 `@tool` 注册中心管理（`core/tools/`），前端只负责展示工具时间轴。
工具分三类风险等级：`read`（自动执行）/ `write` / `exec`（需确认，审计日志记录）。

### 内置工具

| 类别 | 工具 |
|------|------|
| 基础 | `grep_file` `find_files` `read_file` `write_file` `parse_doc` `list_dir` `stat_path` `system_probe` |
| 执行 | `run_shell_tool` `run_python_tool`（超时/流式/可 kill，独立子进程） |
| 检索 | `web_search`（duckduckgo）`get_weather`（wttr.in 免 key）`get_datetime` `calculate`（AST 白名单求值） |
| 记忆 | `memory_get` `memory_put` |
| 定时 | `register_schedule` `list_schedules` `remove_schedule` |
| 技能 | `list_skills` `run_skill_tool` |
| GUI | `gui_activate_tool` `list_windows_tool` `gui_click_tool` `gui_type_tool` `gui_screenshot_tool` |
| MCP | 动态注册 `mcp_<server>_<tool>` |

### 新增一个工具（三步）

```python
# 1. core/tools/xxx.py
from core.tools.base import tool

@tool("按城市查天气", risk="read")
async def get_weather(city: str) -> str:
    return f"{city}: 晴 25°C"
```

2. 在 `core/tools/__init__.py` `import` 该模块触发注册。
3. 重启服务，LLM 会自动发现并调用。

> `read` 级工具并发执行；`write/exec` 串行且逐个人工确认。

## Skills 技能包

`skills/*.yaml` 定义（文件名 = 技能名），热加载（mtime 变化自动重载）：

```yaml
name: 每日天气
description: 查询指定城市天气
requires: [city]
steps:
  - tool: get_weather
    args_template: '{"city": "{{city}}"}'
  - tool: get_datetime
    args_template: '{}'
dangerous: false
```

执行：`{{param}}` 填参 → 逐步骤调工具；`dangerous: true` 需人工确认。
入口：`list_skills` / `run_skill_tool`。

## MCP 桥接

`config.yaml` 的 `mcp.servers` 配置外部 MCP server（stdio transport）：

```yaml
mcp:
  servers:
    - name: echo
      command: py
      args: ["-3.14", "scripts/mcp_echo_server.py"]
```

启动时自动连接并注册其工具为 `mcp_<server>_<tool>`（风险默认 `exec`）。
示例 echo server 见 `scripts/mcp_echo_server.py`。
