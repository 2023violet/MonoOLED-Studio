# TASK-001 — Adopt ChatGPT-Codex development workflow

## Status

VERIFY

## Goal

在 MonoOLED-Studio 中嵌入 AI Workflow Control Plane，同时保留并尊重已有 `AGENTS.md`、`docs/AI_HANDOFF.md`、Git 纪律、用户工作区和兼容性规则。

## Background

项目已有正式的 Agent 入口和开发交接导航，但没有跨 ChatGPT / Codex 共享的 TASK Contract、已确认工作流决定和长期状态目录。本任务只建立维护控制层，不改变产品功能。

## Current Problem

未来任务需要明确：先读取什么、谁负责什么、哪些文件属于已有用户工作、TASK 如何进入验证、谁有权判定 PASS / DONE，以及哪些状态必须动态查询。

## Evidence

- 实施前重新读取了实时 Git 状态、分支、远端、版本和工作区文件。
- 实施前为 8 个用户已有文件建立了 SHA-256 保护基线。
- `.ai/`、`PROJECT_CONTEXT.md` 和 `docs/ai/PROJECT_CONTEXT.md` 在任务开始时不存在。
- `tools/MonoOLEDStudio.spec` 只将 `docs/` 作为 Runtime docs 打包；本控制层位于仓库根目录的 `.ai/`。

## Required Changes

- 在 `.ai/` 建立 workflow protocol、confirmed decisions、current state 和 TASK 目录。
- 在 `AGENTS.md` 增加最小的 AI Workflow Control Plane 导航。
- 保持 `docs/AI_HANDOFF.md` 为架构、兼容性、验证和发布导航真源。

## Out of Scope

- 任何主题 A/B/C 方案选择或主题逻辑修改；
- `DESIGN_SYSTEM`、主题代码和主题测试修改；
- 产品业务代码、测试、构建、发布、依赖或打包规则修改；
- 新建 `PROJECT_CONTEXT.md`；
- 创建 TASK-002 或开始后续产品任务；
- Initial implementation boundary：Git staging、commit、push、PR、tag、release、force push、rebase、stash、clean 均未获授权。

## Review-baseline Publication Authorization

本地实施完成并停在 `VERIFY` / `PENDING` 后，用户随后单独授权建立 GitHub Independent Review Baseline：

- 只暂存 5 个 Workflow 文件；
- 创建 commit：`chore(ai-workflow): adopt ChatGPT-Codex workflow`；
- 正常 fast-forward push 到 `origin/main`；
- 不使用 force push、force-with-lease、rebase、PR、tag、release 或 history rewrite；
- 用户已有主题工作不得进入该 commit。

稳定的 Review Baseline 为：

```text
d1903e1a42cbdaa0b01cd27db1b4b958f66c0d56
```

这段记录描述本地实施完成后的独立授权发布历史，不改变初始实施阶段的 scope，也不属于 `CURRENT_STATE.md` 的瞬时 Git 状态。

## Protected Existing Work

以下文件在任务开始前已有用户工作，必须保持原位置、原内容和未暂存状态：

- `docs/DESIGN_SYSTEM.md`
- `src/qt_theme.py`
- `src/theme_system.py`
- `src/ui_metrics.py`
- `tests/test_qt_theme.py`
- `tests/test_v10_ui_craft_contract.py`
- `BLOCKED.md`
- `PROGRESS.md`

## Constraints

- 只允许修改 `AGENTS.md` 和本任务列出的 `.ai/*` 文件。
- `.ai/` 是 repository-maintenance control plane，不是产品用户文档。
- `CURRENT_STATE.md` 不得保存精确 HEAD、dirty/clean、暂存列表、未跟踪列表、同步或推送状态。
- 受保护文件 before / after SHA-256 必须完全一致；任何变化都构成 `USER WORKSPACE PRESERVATION FAILURE`。
- 不运行完整 pytest，也不运行会因根目录 Markdown hygiene 检查 `BLOCKED.md` / `PROGRESS.md` 的测试。

## Allowed Files / Expected Area

- `AGENTS.md`：末尾新增一段简短的控制层导航；
- `.ai/README.md`；
- `.ai/DECISIONS.md`；
- `.ai/CURRENT_STATE.md`；
- `.ai/tasks/TASK-001.md`。

## Acceptance Criteria

1. 既有 `AGENTS.md` 内容保留，只做最小增量。
2. `docs/AI_HANDOFF.md` 未修改。
3. 没有创建重复的 `PROJECT_CONTEXT.md`。
4. `.ai/` 明确只承担 AI Workflow Control Plane。
5. `.ai/README.md` 定义 User、ChatGPT、Codex 职责和独立 Review 闭环。
6. `.ai/DECISIONS.md` 只包含已确认工作流决定，不包含暗色主题 A/B/C 未决方案。
7. `.ai/CURRENT_STATE.md` 不持久化瞬时 Git 状态。
8. `.ai/tasks/TASK-001.md` 定义本次 Workflow Adoption，最终状态为 `VERIFY`，Review 状态为 `PENDING`。
9. 所有受保护文件 before / after hash 完全一致，并保持未暂存。
10. 没有修改产品业务代码、主题代码、主题测试、构建或发布配置。
11. 没有未经授权的 commit、push、PR、tag 或 release；Review-baseline publication 仅在用户后续明确授权后执行，且该 commit 只包含 `AGENTS.md`、`.ai/README.md`、`.ai/DECISIONS.md`、`.ai/CURRENT_STATE.md` 和 `.ai/tasks/TASK-001.md`，用户已有主题工作没有进入该 commit，也没有使用 PR、tag、release、force push、rebase 或 history rewrite。
12. 新 Codex 会话能够识别 active TASK、受保护工作、权威层级、验证方式和独立 Review 责任。

## Verification Plan

- 重新读取实时 `git status --short --branch`、分支、远端和版本信息；
- 计算受保护文件 SHA-256 before 基线；
- 检查授权范围内的 diff；
- 执行 `git diff --check`；
- 检查 `AGENTS.md` 和 `.ai/` 内容一致性；
- 计算受保护文件 SHA-256 after，并逐项确认 before == after；
- 确认受保护文件仍未暂存；
- 不运行完整 pytest、构建、发布或产品 smoke。

## Deliverables

- `AGENTS.md` 的最小 AI Workflow Control Plane 导航；
- `.ai/README.md`；
- `.ai/DECISIONS.md`；
- `.ai/CURRENT_STATE.md`；
- `.ai/tasks/TASK-001.md`；
- 最终独立审查报告所需的 diff、scope 和 hash 证据。

## Result

TASK-001 的 local implementation 已先在授权范围内完成，并停在 `VERIFY` / `PENDING`。随后用户单独授权建立 GitHub Independent Review Baseline；Review baseline 为 `d1903e1a42cbdaa0b01cd27db1b4b958f66c0d56`，已使用指定 commit message 正常 fast-forward push 到 `origin/main`。现有产品主题工作保持为独立的用户工作区，未被本任务决策、修改或提交。当前任务仍等待 ChatGPT 独立 Review。

## Review Status

PENDING
