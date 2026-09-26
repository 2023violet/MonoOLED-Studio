# ChatGPT × Codex Workflow Protocol

`.ai/` 是 MonoOLED Studio 的 repository-maintenance control plane。它保存跨会话的任务契约、已确认决定和长期工作状态，不替代产品文档、架构导航或实时代码事实。

## Generated Context

`tools/BUILD_AI_CONTEXT.py` 可生成 `.ai/GENERATED_CONTEXT.md` 作为冷启动导航索引。该文件由权威源派生、已被 Git 忽略、可删除并可重建，可能因仓库状态变化而过期；它不是 authority，重要决定前必须重新生成并读取 live Git、active TASK、源码、测试和控制面文件。生成器只读，不会自动修改 `DECISIONS.md`、`CURRENT_STATE.md` 或 `docs/AI_HANDOFF.md`，也不应创建第二份项目上下文真源。

产品架构、兼容性、验证和发布导航继续以 [`docs/AI_HANDOFF.md`](../docs/AI_HANDOFF.md) 为真源。`.ai/` 不建立 `PROJECT_CONTEXT.md`，也不进入 `docs/README.md` 的产品文档索引。

## Authority and read order

判断项目事实时按以下顺序处理：

1. 用户当前明确目标与限制；
2. `AGENTS.md`；
3. 实时仓库事实：Git、源码、测试、机器可读契约、版本和清单；
4. 用户已经确认且仍有效的 `.ai/DECISIONS.md`；
5. `docs/AI_HANDOFF.md` 的架构导航、兼容性和验证说明；
6. `.ai/CURRENT_STATE.md`；
7. AI 对话总结。

如果这些层级冲突，报告 `AUTHORITY CONFLICT`，不要自行选取一个结果。TASK 只规定本轮 scope、限制、验收和验证方式；如果 TASK 假设与仓库事实冲突，报告 `TASK ASSUMPTION CONFLICT`。

## Roles

### User

- 做最终产品决定；
- 授权实施、确认 scope；
- 批准高风险或外部操作；
- 决定未决产品方案。

### ChatGPT

```text
需求澄清
→ 读取 GitHub / 权威资料
→ 分析
→ 生成 TASK Contract
→ 独立 Review
→ PASS / REWORK REQUIRED
```

ChatGPT 不因为 Codex 声称 `done` 或 `all tests passed` 就直接判定完成，必须重新读取证据。

### Codex

```text
READ
→ VERIFY ASSUMPTIONS
→ SCOPE
→ ESTABLISH FAILURE EVIDENCE
→ IMPLEMENT
→ TEST
→ DIFF REVIEW
→ REPORT
→ VERIFY
```

Codex 必须保护进入任务前的用户修改，区分 `PRE-EXISTING USER WORK` 和本轮 TASK 改动，并按实际运行结果报告验证。Codex 不得自行把 `VERIFY` 推进为 `DONE`，也不得把 `PENDING` 推进为 `PASS`。

## TASK lifecycle

```text
DRAFT → APPROVED → IN_PROGRESS → VERIFY → DONE
```

独立 Review 结果只有 `PASS` 或 `REWORK REQUIRED`。出现 `REWORK REQUIRED` 时，必须形成明确修复范围；Codex 不应无限扩大范围自行修复。

每个任务文件使用以下结构：

```text
Status
Goal
Background
Current Problem
Evidence
Required Changes
Out of Scope
Protected Existing Work
Constraints
Allowed Files / Expected Area
Acceptance Criteria
Verification Plan
Deliverables
Result
Review Status
```

## Operating rules

- 任务开始时先读取本文件、`AGENTS.md`、相关 `docs/AI_HANDOFF.md` 章节和 active TASK。
- 进入任务时已有的修改、未跟踪文件和本地证据均属于受保护上下文，除非用户明确授权，不得清理、覆盖、暂存、提交或共享。
- 瞬时 Git 状态必须在执行前动态查询；长期状态文件不得保存精确 HEAD、dirty/clean、暂存列表、未跟踪列表或推送状态。
- 没有用户明确授权时，不执行 push、PR、tag、release、force push、rebase、stash 或 clean。
- 验证命令必须与任务风险匹配，并报告实际运行的命令、结果、跳过项和未运行门禁。

## Rust V2 validation namespace

Rust V2 的验证性决策和阶段计划位于 `.ai/rust/`：

- `.ai/rust/ADR-001.md`：Rust 命名空间的 Validation 决策；全局 `.ai/DECISIONS.md` 中对应编号为 ADR-005；
- `.ai/rust/VALIDATION_PLAN.md`：四个 Gate、语义兼容性、平台证据与 Phase 1 退出条件；
- `.ai/rust/PHASE-0.md`：当前隔离与 Golden Baseline 契约。
- `.ai/rust/PHASE-1.md` 与 `.ai/rust/PHASE-1-REPORT.md`：当前 Pixel Slice 实现、验证证据与剩余门禁；
- `.ai/rust/PHASE-1-EVIDENCE.md`：GUI 交互、DPI、长任务、worker 关闭与三平台冒烟证据记录；
- `.ai/rust/PHASE-1-REVIEW-REQUEST.md`：Phase 1 证据的独立 Review 请求（当前待审）；
- `.ai/rust/CLEAN_HANDOFF.md`：新人接手所需的 worktree 边界、已验证事实和下一步。

它们不替代 `AGENTS.md`、实时 Git、源码、测试或 `docs/AI_HANDOFF.md`。从
Rust 分支接手时先读 `CLEAN_HANDOFF.md`，然后按其中的 live Git 顺序复核。
