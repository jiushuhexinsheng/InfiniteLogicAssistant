---
name: executing-plans
description: Use when you have a written implementation plan to execute in a separate session with review checkpoints
---

<!-- DSH-ADAPTED: migrated from Claude Code skill. Do not edit this block. -->

> **DSH 适配说明(由 Claude Code 技能转换)**
> 本技能原为 Claude Code 插件技能,现迁移到 DeepSeek Harness(DSH)。执行时请使用 DSH 工具:
> - Shell 命令(`Bash`/`Terminal`)→ `pwsh` 工具(Windows)
> - 文件搜索与读取(`Grep`/`Glob`/`Read`)→ `grep` / `glob` / `read` 工具
> - 文件修改(`Write`/`Edit`/`MultiEdit`)→ `write` / `edit` 工具
> - 联网检索(`WebSearch`/`WebFetch`)→ `web_search` 工具(未开启网页抓取时,优先用搜索并引用来源)
> - 子代理(`Task`/`Agent`)→ `subagent` / `subagent_fork`(默认后台运行)
> - 任务清单(`TodoWrite`)→ `todo_write`
> - 文中提到的 Claude 专属 MCP 工具仅在 DSH 中连接对应 MCP server 后才可用;未连接时向用户说明限制并给出替代方案。
> 其余流程性指引保持不变。


# Executing Plans

## Overview

Load plan, review critically, execute all tasks, report when complete.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

**Note:** Tell your human partner that Superpowers works much better with access to subagents (Claude Code, Codex CLI, Codex App, Copilot CLI, and Gemini CLI all qualify; see the per-platform tool refs in `../using-superpowers/references/`). If subagents are available, use superpowers:subagent-driven-development instead of this skill.

## The Process

### Step 1: Load and Review Plan
1. Ensure an isolated workspace: use superpowers:using-git-worktrees to create one or verify the existing one
2. Read plan file
3. Review critically - identify any questions or concerns about the plan
4. If concerns: Raise them with your human partner before starting
5. If no concerns: Create todos for the plan items and proceed

### Step 2: Execute Tasks

For each task:
1. Mark as in_progress
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified
4. Mark as completed

### Step 3: Complete Development

After all tasks complete and verified:
- Announce: "I'm using the finishing-a-development-branch skill to complete this work."
- **REQUIRED SUB-SKILL:** Use superpowers:finishing-a-development-branch
- Follow that skill to verify tests, present options, execute choice

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Remember
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Stop when blocked, don't guess
- Never start implementation on main/master branch without explicit user consent
