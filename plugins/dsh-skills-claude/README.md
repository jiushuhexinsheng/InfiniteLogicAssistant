# dsh-skills-claude

DSH(DeepSeek Harness)插件:把从 Claude Code 插件转换来的技能打包为内置技能源(provider 名 `claude-skills`)。

包含 34 个技能(均带 DSH 适配说明头),来源:

| 来源插件 | 技能数 |
|---|---|
| superpowers 6.3.0 | 14 |
| figma 2.2.95(含 2 个 workflow 技能) | 14 |
| frontend-design | 1 |
| qodo 0.6.1 | 2 |
| mcp-server-dev | 3 |

## 工作原理

- 插件复用 `@deepseek-ai/dsh-skill-filesystem` 的 bundled 技能机制(`trustedHost` 根、`BUNDLED_SKILL_RANK` 排序、与内置技能根完全一致的发现/解析/热更新行为)。
- `includeDefaultRoots: false`,只注册本包 `skills/` 目录,不影响项目/用户技能根。
- loader 行加在 profile 根组合(全局层),所有 preset 的技能目录都会合并它。

## 安装

### 方式 A:通过 dsh 命令(需要 pnpm)

```bash
dsh plugin --profile web add <本包路径或已发布的包名>
```

然后把 loader 行加入 `~/.dsh/profiles/web/cordis.patch.yml`:

```yaml
- insert:
    - id: dsh-skills-claude
      name: dsh-skills-claude
```

`cordis.patch.yml` 会被 DSH 热加载(HMR),无需重启。

### 方式 B:手动(本机当前做法,pnpm 不可用时)

1. 把本包复制到 profile 的 hoisted node_modules(loader 以 profile 目录为 baseUrl 向上解析):

   ```powershell
   Copy-Item -Path . -Destination "$env:USERPROFILE\.dsh\profiles\node_modules\dsh-skills-claude" -Recurse -Force
   ```

2. 同上在 `~/.dsh/profiles/web/cordis.patch.yml` 插入 loader 行。

## 卸载

- 从 `cordis.patch.yml` 删除对应 insert 块(热生效)。
- 删除 `profiles/node_modules/dsh-skills-claude` 目录。

## 与 ~/.dsh/skills 的关系

如果 `~/.dsh/skills` 下已有同名技能副本,两者内容一致:
预设层(project/user 根)在层合并时优先于全局层,所以目录副本会赢;想完全由插件提供,删除 `~/.dsh/skills` 下的同名目录即可。

## 开发

`skills/` 目录内容来自 Claude Code 插件缓存(`~/.claude/plugins/cache/claude-plugins-official/` 下已安装插件的 `skills/` 与 `workflow-skills/`),已内嵌 DSH 适配说明头。插件更新后如需重新同步,直接复制对应技能目录覆盖本包 `skills/` 下同名目录即可。
