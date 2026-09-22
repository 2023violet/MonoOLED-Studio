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
- Git staging、commit、push、PR、tag、release、force push、rebase、stash、clean。

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
11. 没有新增依赖、提交、推送、PR、tag 或 release。
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

TASK-001 的 workflow control plane 已在授权范围内建立。现有产品主题工作保持为独立的用户工作区，未被本任务决策或修改。等待 ChatGPT 独立 Review。

## Review Status

PENDING
